import logging
import httpx
import asyncio
from uuid import UUID
from typing import List, Dict, Any

from agent import client as agent_client
from agent.models import AgentModel
from mcp_servers.imap_mcpserver.src.imap_client.client import get_all_labels, get_messages_from_folder
from mcp_servers.imap_mcpserver.src.imap_client.models import EmailMessage
from shared.config import settings

logger = logging.getLogger(__name__)

async def _get_llm_response(prompt: str, model: str) -> str:
    """
    Makes a call to an LLM to get a response for a given prompt.
    """
    try:
        # Use a generic endpoint if possible, or configure based on model provider
        # For this temporary solution, we can hardcode the OpenRouter endpoint
        api_url = "https://openrouter.ai/api/v1/chat/completions"
        api_key = settings.OPENROUTER_API_KEY

        if not api_key:
            logger.error("OpenRouter API key is not configured.")
            return "Error: LLM service not configured."

        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        logger.error(f"LLM API request failed with status {e.response.status_code}: {e.response.text}")
        return f"Error: LLM request failed with status {e.response.status_code}."
    except Exception as e:
        logger.error(f"An unexpected error occurred during LLM request: {e}", exc_info=True)
        return "Error: An unexpected error occurred while contacting the LLM."

async def _process_single_label(label_name: str) -> tuple[str, str | None]:
    """
    Fetches emails for a single label and generates a description.
    Returns the label name and the new description, or None if it fails.
    """
    logger.info(f"Processing label: {label_name}")
    # Fetch up to 10 sample emails for the label
    sample_emails = await get_messages_from_folder(label_name, count=10)

    if not sample_emails:
        logger.info(f"No emails found for label '{label_name}'. Skipping.")
        return label_name, None
    
    logger.info(f"Found {len(sample_emails)} emails for label '{label_name}'. Generating description.")

    # Generate a new description using the LLM
    prompt = _build_llm_prompt(sample_emails, label_name)
    # Use a dedicated, fast model for description generation
    new_description = await _get_llm_response(prompt, "google/gemini-2.5-flash")

    if new_description.startswith("Error:"):
        logger.error(f"Could not generate description for {label_name}: {new_description}")
        return label_name, None
    
    return label_name, new_description


def _build_llm_prompt(emails: List[EmailMessage], label_name: str) -> str:
    """
    Builds a detailed prompt for the LLM to generate a label description.
    """
    email_summaries = []
    for i, email in enumerate(emails, 1):
        # Decode subject if needed
        subject = email.subject
        from_ = email.from_
        snippet = (email.body_cleaned[:200] + '...') if len(email.body_cleaned) > 200 else email.body_cleaned
        
        summary = f"Email {i}:\n"
        summary += f"From: {from_}\n"
        summary += f"Subject: {subject}\n"
        summary += f"Snippet: {snippet}\n"
        email_summaries.append(summary)

    prompt = (
        f"You are an expert AI assistant tasked with creating a concise and accurate description for an email label based on a sample of emails.\n\n"
        f"The label is named: '{label_name}'\n\n"
        f"Here are {len(emails)} sample emails that have been assigned this label:\n\n"
        f"{'---'.join(email_summaries)}\n\n"
        f"Based on these examples, please generate a summary description that captures the essence of what this label represents. "
        f"The description should be clear and helpful for a user to understand when this label should be applied. It should include examples of the type of emails that should be labeled with this label. Be specific"
        f"Focus on the common themes, senders, or content types. Do not include any preamble, just the description itself."
    )
    return prompt

async def generate_descriptions_for_agent(agent_uuid: UUID) -> AgentModel | None:
    """
    Fetches labels, analyzes emails, and updates an agent's label descriptions in parallel.
    Returns the updated agent model.
    """
    logger.info(f"Starting label description generation for agent {agent_uuid}")
    try:
        agent = await agent_client.get_agent(agent_uuid)
        if not agent:
            logger.error(f"Agent with UUID {agent_uuid} not found.")
            return None

        # 1. Fetch all available labels from the IMAP server
        available_labels = await get_all_labels()
        if not available_labels:
            logger.warning("No labels found in the user's inbox.")
            return agent

        logger.info(f"Found {len(available_labels)} labels in inbox: {available_labels}")
        
        # 2. Get the agent's current labeling rules
        agent_param_values = agent.param_values or {}
        labeling_rules = agent_param_values.get("labeling_rules", [])
        
        # If no rules are defined, create them from the user's inbox labels
        if not labeling_rules:
            logger.info(f"Agent {agent_uuid} has no labeling_rules. Populating from inbox labels.")
            # Exclude common system/unwanted labels
            excluded_labels = {'INBOX', '[Gmail]'}
            labels_from_inbox = [lbl for lbl in available_labels if lbl not in excluded_labels and not lbl.startswith('[Gmail]/')]
            
            labeling_rules = [
                {"label_name": label_name, "label_description": ""}
                for label_name in labels_from_inbox
            ]
            # Set this on the agent's param_values to ensure it gets saved later
            agent.param_values["labeling_rules"] = labeling_rules
            logger.info(f"Populated with {len(labeling_rules)} rules from inbox.")


        configured_labels = {rule.get("label_name") for rule in labeling_rules}
        logger.info(f"Agent is configured with labels: {configured_labels}")

        # 3. Find intersection of configured labels and available labels
        labels_to_process = [label for label in available_labels if label in configured_labels]
        logger.info(f"Will process matching labels: {labels_to_process}")

        # 4. Create and run description generation tasks in parallel
        tasks = [_process_single_label(label_name) for label_name in labels_to_process]
        results = await asyncio.gather(*tasks)

        # 5. Update descriptions based on parallel task results
        descriptions_updated = False
        new_descriptions = {label_name: desc for label_name, desc in results if desc}
        
        for rule in labeling_rules:
            label_name = rule.get("label_name")
            if label_name in new_descriptions:
                rule["label_description"] = new_descriptions[label_name]
                logger.info(f"Updated description for '{label_name}': '{new_descriptions[label_name]}'")
                descriptions_updated = True
        
        # 6. Save the agent if any descriptions were updated
        if descriptions_updated:
            agent.param_values["labeling_rules"] = labeling_rules
            await agent_client.save_agent(agent)
            logger.info(f"Successfully saved updated descriptions for agent {agent_uuid}")
        else:
            logger.info(f"No descriptions were updated for agent {agent_uuid}.")
        
        return agent

    except Exception as e:
        logger.error(f"An error occurred during label description generation for agent {agent_uuid}: {e}", exc_info=True)
        return None 
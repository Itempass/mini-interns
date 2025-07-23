import logging
import os
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
import json
from pathlib import Path
import httpx
import asyncio

from mcp_servers.imap_mcpserver.src.imap_client.client import (
    get_all_labels,
    get_messages_from_folder,
)
from mcp_servers.imap_mcpserver.src.imap_client.models import EmailMessage
from shared.config import settings

import workflow.agent_client as agent_client
import workflow.client as workflow_client
import workflow.llm_client as llm_client
import workflow.trigger_client as trigger_client
from workflow_agent.mcp.dependencies import get_context_from_headers
from workflow_agent.mcp.mcp_builder import mcp_builder
from workflow_agent.mcp.prompt_validator import validate_prompt_references

logger = logging.getLogger(__name__)


def get_valid_llm_model_ids() -> List[str]:
    """Helper to load valid LLM model IDs from the JSON file."""
    models_path = Path(__file__).parent.parent.parent / "shared/llm_models.json"
    try:
        with open(models_path, "r") as f:
            models = json.load(f)
        return [model["id"] for model in models]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return []

VALID_LLM_MODELS = get_valid_llm_model_ids()
API_BASE_URL = "https://mini-logs.cloud1.itempasshomelab.org"
#API_BASE_URL = "http://host.docker.internal:5000"


@mcp_builder.tool()
async def feature_request(suggested_name: str, suggested_description: str) -> str:
    """
    Submits a feature request to the backend. Call this when you have a clear
    idea for a new feature. The system will process the request and store it.
    """
    context = get_context_from_headers()
    user_id = str(context.user_id)

    logger.info(
        f"--- Submitting Feature Request ---\n"
        f"Name: {suggested_name}\n"
        f"Description: {suggested_description}\n"
        f"User ID: {user_id}\n"
        f"---------------------------------"
    )

    payload = {
        "user_id": user_id,
        "user_input": {
            "name": suggested_name,
            "description": suggested_description,
        },
    }

    logger.info(f"Submitting feature request to {API_BASE_URL} with payload: {payload}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_BASE_URL}/api/v2/feature_request",
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            logger.info(f"Feature request submitted successfully. Status code: {response.status_code}")
            confirmation_message = (
                f"Feature request '{suggested_name}' has been successfully submitted. "
                "Acknowledge this and ask how else I can help."
            )
            return confirmation_message
    except httpx.HTTPStatusError as e:
        error_message = f"Failed to submit feature request. Status code: {e.response.status_code}, Response: {e.response.text}"
        logger.error(error_message)
        return error_message
    except Exception as e:
        error_message = f"An unexpected error occurred while submitting the feature request: {e}"
        logger.error(error_message, exc_info=True)
        return error_message


@mcp_builder.tool()
async def get_workflow_details() -> dict:
    """
    Retrieves the full, detailed configuration of a specific workflow, including its name, description, trigger, and all of its steps in order.
    You can use <<trigger_output>> or <<step_output.[step uuid]>> to reference the trigger output or the output of a previous step.
    """
    context = get_context_from_headers()
    workflow = await workflow_client.get_with_details(
        workflow_uuid=context.workflow_uuid, user_id=context.user_id
    )
    return workflow.model_dump() if workflow else None


@mcp_builder.tool()
async def list_available_triggers() -> List[dict]:
    """
    Returns a list of all available trigger types that can be used to start a workflow. Each trigger type includes its 'id', 'name', and 'description'.
    """
    return await workflow_client.list_available_trigger_types()


@mcp_builder.tool()
async def set_trigger(trigger_type_id: str) -> dict:
    """
    Sets or replaces the trigger for a specific workflow. Use 'list_available_triggers' to find the correct 'trigger_type_id'. 
    You can use <<trigger_output>> to reference the trigger output.
    """
    context = get_context_from_headers()
    workflow = await workflow_client.set_trigger(
        workflow_uuid=context.workflow_uuid,
        trigger_type_id=trigger_type_id,
        user_id=context.user_id,
    )
    return workflow.model_dump()


@mcp_builder.tool()
async def update_trigger_settings(
    trigger_uuid: str,
    filter_rules: dict,
) -> dict:
    """
    Updates the settings of an existing trigger. The 'filter_rules' determine the conditions under which the workflow runs. The 'trigger_uuid' can be found in the workflow details. Returns the updated `TriggerModel`.
    """
    context = get_context_from_headers()
    trigger = await trigger_client.get(
        uuid=UUID(trigger_uuid), user_id=context.user_id
    )
    if not trigger:
        raise ValueError("Trigger not found")
    trigger.filter_rules = filter_rules
    updated_trigger = await trigger_client.update(trigger, user_id=context.user_id)
    return updated_trigger.model_dump()


@mcp_builder.tool()
async def list_available_step_types() -> List[dict]:
    """
    Returns a list of all available step types that can be added to a workflow, such as 'custom_llm' or 'custom_agent'.
    """
    return await workflow_client.list_available_step_types()


@mcp_builder.tool()
async def add_step(
    step_type: str,
    name: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Adds a new step to the end of a specified workflow, optionally setting its system prompt and model.
    Use 'list_available_step_types' to see valid options for 'step_type'.
    The 'model' is only applicable for 'custom_llm' and 'custom_agent' step types.
    You can use <<trigger_output>> or <<step_output.[step uuid]>> to reference the trigger output or the output of a previous step.
    """
    if model and model not in VALID_LLM_MODELS:
        raise ValueError(f"Invalid model ID: '{model}'. Must be one of {VALID_LLM_MODELS}")

    context = get_context_from_headers()
    user_uuid = context.user_id
    workflow_uuid = context.workflow_uuid

    if system_prompt:
        workflow = await workflow_client.get_with_details(workflow_uuid, user_uuid)
        if not workflow:
            raise ValueError("Workflow not found")
        validate_prompt_references(system_prompt, workflow, uuid4())


    workflow = await workflow_client.add_new_step(
        workflow_uuid=workflow_uuid,
        step_type=step_type,
        name=name,
        user_id=user_uuid,
        model=model,
    )

    if system_prompt and step_type in ["custom_llm", "custom_agent"]:
        new_step_uuid = workflow.steps[-1]

        step_to_update = None
        if step_type == "custom_llm":
            step_to_update = await llm_client.get(uuid=new_step_uuid, user_id=user_uuid)
        elif step_type == "custom_agent":
            step_to_update = await agent_client.get(
                uuid=new_step_uuid, user_id=user_uuid
            )

        if not step_to_update:
            raise ValueError("Newly added step not found. This should not happen.")

        step_to_update.system_prompt = system_prompt
        await workflow_client.update_step(step_to_update, user_uuid)

    workflow = await workflow_client.get_with_details(workflow_uuid, user_uuid)

    return workflow.model_dump()


@mcp_builder.tool()
async def remove_step(step_uuid: str) -> None:
    """
    Removes a specific step from a workflow. The agent can find the 'step_uuid' from the workflow details.
    """
    context = get_context_from_headers()
    await workflow_client.delete_step(
        workflow_uuid=context.workflow_uuid,
        step_uuid=UUID(step_uuid),
        user_id=context.user_id,
    )
    return None


@mcp_builder.tool()
async def reorder_steps(ordered_step_uuids: List[str]) -> dict:
    """
    Changes the execution order of steps in a workflow. Provide the full list of 'step_uuid's in the desired new order. Make sure to check the system prompts afterwards to see if the output references (<<trigger_output>> or <<step_output.[step uuid]>>) are correct.
    """
    context = get_context_from_headers()
    ordered_uuids = [UUID(uuid) for uuid in ordered_step_uuids]
    workflow = await workflow_client.reorder_steps(
        workflow_uuid=context.workflow_uuid,
        ordered_step_uuids=ordered_uuids,
        user_id=context.user_id,
    )
    return workflow.model_dump()


@mcp_builder.tool()
async def update_system_prompt_for_step(
    step_uuid: str,
    system_prompt: str,
) -> dict:
    """
    Updates the system prompt for a specific workflow step. This works for steps of type 'custom_llm' or 'custom_agent'. Use <<trigger_output>> or <<step_output.[step uuid]>> to reference the trigger output or the output of a previous step.
    """
    context = get_context_from_headers()
    user_uuid = context.user_id
    workflow = await workflow_client.get_with_details(context.workflow_uuid, user_uuid)
    if not workflow:
        raise ValueError("Workflow not found")

    step_to_update = next((s for s in workflow.steps if str(s.uuid) == step_uuid), None)
    if not step_to_update:
        raise ValueError("Step not found in workflow")
    
    validate_prompt_references(system_prompt, workflow, step_to_update.uuid)

    if not hasattr(step_to_update, "system_prompt"):
        raise TypeError(
            f"Step of type {step_to_update.type} does not have a system_prompt attribute."
        )

    step_to_update.system_prompt = system_prompt
    updated_step = await workflow_client.update_step(step_to_update, user_uuid)
    return updated_step.model_dump()


@mcp_builder.tool()
async def update_step_model(
    step_uuid: str,
    model: str,
) -> dict:
    """
    Updates the model for a specific workflow step. This works for steps of type 'custom_llm' or 'custom_agent'.
    """
    if model not in VALID_LLM_MODELS:
        raise ValueError(f"Invalid model ID: '{model}'. Must be one of {VALID_LLM_MODELS}")

    context = get_context_from_headers()
    user_uuid = context.user_id
    workflow = await workflow_client.get_with_details(context.workflow_uuid, user_uuid)
    if not workflow:
        raise ValueError("Workflow not found")

    step_to_update = next((s for s in workflow.steps if str(s.uuid) == step_uuid), None)
    if not step_to_update:
        raise ValueError("Step not found in workflow")

    if not hasattr(step_to_update, "model"):
        raise TypeError(
            f"Step of type {step_to_update.type} does not have a model attribute."
        )

    step_to_update.model = model
    updated_step = await workflow_client.update_step(step_to_update, user_uuid)
    return updated_step.model_dump()


@mcp_builder.tool()
async def list_available_mcp_tools() -> List[dict]:
    """
    Returns a list of all available tools from all connected MCP servers that can be enabled for an agent step.
    """
    return await workflow_client.discover_mcp_tools()


@mcp_builder.tool()
async def update_step_mcp_tools(
    step_uuid: str,
    enabled_tools: List[str],
) -> dict:
    """
    Updates the set of enabled tools for a specific agent step. This only works for steps of type 'custom_agent'. Provide the full list of tool names that should be enabled. Returns the updated step model.
    """
    context = get_context_from_headers()
    user_uuid = context.user_id
    workflow = await workflow_client.get_with_details(context.workflow_uuid, user_uuid)
    if not workflow:
        raise ValueError("Workflow not found")

    step_to_update = next((s for s in workflow.steps if str(s.uuid) == step_uuid), None)
    if not step_to_update:
        raise ValueError("Step not found in workflow")

    if step_to_update.type != "custom_agent":
        raise TypeError(
            "MCP tools can only be updated for steps of type 'custom_agent'."
        )

    # The tools attribute is a dictionary where keys are tool names (e.g., 'imap-mcp-server-send_email')
    # and values are dictionaries indicating if the tool is enabled.
    new_tools_dict = {}
    for tool_name in enabled_tools:
        new_tools_dict[tool_name] = {"enabled": True}

    step_to_update.tools = new_tools_dict
    updated_step = await workflow_client.update_step(step_to_update, user_uuid)
    return updated_step.model_dump()


@mcp_builder.tool()
async def update_checker_step_settings(
    step_uuid: str,
    check_mode: str,
    match_values: List[str],
    step_to_check_uuid: Optional[str] = None,
) -> dict:
    """
    Updates the settings for a 'stop_checker' step. This step performs a simple,
    case-insensitive text search on the output of a previous step.

    The output of the step being checked (e.g., a JSON object) is converted to a
    plain text string before the check is performed.

    Args:
        step_uuid: The UUID of the checker step to update.
        check_mode: The condition to check for. Must be either 'stop_if_output_contains' or 'continue_if_output_contains'.
        match_values: A list of strings to search for in the output text. If any value is found, the condition is met.
        step_to_check_uuid: The UUID of the preceding step whose output should be checked.
    """
    context = get_context_from_headers()
    user_uuid = context.user_id
    workflow_uuid = context.workflow_uuid

    if check_mode not in ["stop_if_output_contains", "continue_if_output_contains"]:
        raise ValueError("Invalid check_mode. Must be 'stop_if_output_contains' or 'continue_if_output_contains'.")

    workflow = await workflow_client.get_with_details(workflow_uuid, user_uuid)
    if not workflow:
        raise ValueError("Workflow not found")

    step_to_update = next((s for s in workflow.steps if str(s.uuid) == step_uuid), None)
    if not step_to_update:
        raise ValueError(f"Step with UUID '{step_uuid}' not found in workflow.")

    if step_to_update.type != "stop_checker":
        raise TypeError("This tool can only be used on steps of type 'stop_checker'.")

    # Validate that step_to_check_uuid is a real preceding step
    if step_to_check_uuid:
        step_index = -1
        for i, step in enumerate(workflow.steps):
            if str(step.uuid) == step_uuid:
                step_index = i
                break
        
        preceding_step_uuids = {str(s.uuid) for s in workflow.steps[:step_index]}
        if step_to_check_uuid not in preceding_step_uuids:
            raise ValueError(f"Step UUID '{step_to_check_uuid}' is not a valid preceding step for the checker.")

    step_to_update.step_to_check_uuid = UUID(step_to_check_uuid) if step_to_check_uuid else None
    step_to_update.check_mode = check_mode
    step_to_update.match_values = match_values

    updated_step = await workflow_client.update_step(step_to_update, user_uuid)
    return updated_step.model_dump()


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
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        logger.error(
            f"LLM API request failed with status {e.response.status_code}: {e.response.text}"
        )
        return f"Error: LLM request failed with status {e.response.status_code}."
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during LLM request: {e}", exc_info=True
        )
        return "Error: An unexpected error occurred while contacting the LLM."


def _build_llm_prompt(emails: List[EmailMessage], label_name: str) -> str:
    """
    Builds a detailed prompt for the LLM to generate a label description.
    """
    email_summaries = []
    for i, email in enumerate(emails, 1):
        # Decode subject if needed
        subject = email.subject
        from_ = email.from_
        snippet = (
            (email.body_cleaned[:200] + "...")
            if len(email.body_cleaned) > 200
            else email.body_cleaned
        )

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


async def _process_single_label(user_uuid: UUID, label_name: str) -> tuple[str, str | None]:
    """
    Fetches emails for a single label and generates a description.
    Returns the label name and the new description, or None if it fails.
    """
    logger.info(f"Processing label: {label_name}")
    # Fetch up to 10 sample emails for the label
    sample_emails = await get_messages_from_folder(user_uuid=user_uuid, folder_name=label_name, count=10)

    if not sample_emails:
        logger.info(f"No emails found for label '{label_name}'. Skipping.")
        return label_name, None

    logger.info(
        f"Found {len(sample_emails)} emails for label '{label_name}'. Generating description."
    )

    # Generate a new description using the LLM
    prompt = _build_llm_prompt(sample_emails, label_name)
    # Use a dedicated, fast model for description generation
    new_description = await _get_llm_response(prompt, "google/gemini-2.5-flash")

    if new_description.startswith("Error:"):
        logger.error(f"Could not generate description for {label_name}: {new_description}")
        return label_name, None

    return label_name, new_description


@mcp_builder.tool()
async def get_email_labels_with_descriptions() -> str:
    """
    Fetches all labels from the user's email inbox, generates a description for each based on its content,
    and returns them as a markdown formatted list. This is useful for understanding how emails are currently organized.
    """
    logger.info("Starting label description generation from tool.")
    context = get_context_from_headers()
    try:
        # 1. Fetch all available labels from the IMAP server
        available_labels = await get_all_labels(user_uuid=context.user_id)
        if not available_labels:
            logger.warning("No labels found in the user's inbox.")
            return "No labels found in your inbox."

        logger.info(f"Found {len(available_labels)} labels in inbox: {available_labels}")

        # 2. Create and run description generation tasks in parallel
        tasks = [_process_single_label(user_uuid=context.user_id, label_name=label_name) for label_name in available_labels]
        results = await asyncio.gather(*tasks)

        # 3. Format results into markdown
        markdown_output = (
            "Here are your email labels and their generated descriptions:\n\n"
        )
        descriptions_found = False
        for label_name, desc in results:
            if desc:
                markdown_output += f"* **{label_name}**: {desc}\n"
                descriptions_found = True

        if not descriptions_found:
            return "Could not generate descriptions for any of your labels. This might be because they are all empty."

        return markdown_output

    except Exception as e:
        logger.error(
            f"An error occurred during label description generation: {e}", exc_info=True
        )
        return "Sorry, an unexpected error occurred while generating label descriptions." 
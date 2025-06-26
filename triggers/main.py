import logging
import time
import requests
import asyncio
from imap_tools import MailBox, A
from shared.app_settings import load_app_settings
from shared.redis.keys import RedisKeys
from shared.redis.redis_client import get_redis_client
from triggers.rules import passes_filter
from agent import client as agent_client
from shared.config import settings
import json
from mcp_servers.imap_mcpserver.src.imap_client import client as imap_client
from openai import OpenAI
from agentlogger.src.models import ConversationData, Message, Metadata
from datetime import datetime
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_last_uid():
    """Gets the last processed UID from Redis."""
    redis_client = get_redis_client()
    uid = redis_client.get(RedisKeys.LAST_EMAIL_UID)
    return uid if uid else None

def set_last_uid(uid: str):
    """Sets the last processed UID in Redis."""
    redis_client = get_redis_client()
    redis_client.set(RedisKeys.LAST_EMAIL_UID, uid)

async def passes_trigger_conditions_check(msg, trigger_conditions: str, app_settings, thread_context: str, message_id: str) -> bool:
    """
    Uses an LLM to check if the email passes the trigger conditions.
    Now uses full thread context for more informed trigger decisions.
    """
    logger.info("Performing LLM-based trigger check with thread context...")
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    trigger_conditions_with_date = trigger_conditions.replace("<<CURRENT_DATE>>", f"{current_date} (format YYYY-MM-DD)")

    if not thread_context:
        logger.warning("No thread context provided to trigger check, falling back to single message")
        email_body = msg.text or msg.html
        if not email_body:
            logger.info("Email has no body, skipping LLM trigger check and returning False.")
            return False

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=app_settings.OPENROUTER_API_KEY,
    )
    
    system_prompt = f"""
You are a helpful assistant that determines if an email meets a user's criteria.
Your task is to analyze the email thread in the user message based on the following criteria:
---
{trigger_conditions_with_date}
---
Based on the criteria, decide if the email thread given by the user should be processed.
Consider the full conversation context when making your decision.
Respond with a single JSON object in the format: {{"should_process": true}} or {{"should_process": false}}.
"""

    if thread_context:
        user_prompt = f"""
This is the email thread to be evaluated for processing:

TRIGGERING MESSAGE ID: {message_id}

{thread_context}

Please evaluate whether this email thread should be processed based on the criteria provided.
Focus on the triggering message while considering the full conversation context.
"""
    else:
        # Fallback to single message
        email_body = msg.text or msg.html
        user_prompt = f"""
This is the email to be processed (single message - no thread context available):
Message-ID: {message_id}
From: {msg.from_}
To: {", ".join(msg.to)}
Date: {msg.date_str}
Subject: {msg.subject}
Body:
{email_body[:4000]}
"""
    
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model=app_settings.OPENROUTER_MODEL,
            messages=messages_for_llm,
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        response_content = completion.choices[0].message.content
        logger.info(f"LLM trigger check raw response: '{response_content}'")
        
        messages.append({"role": "assistant", "content": response_content})
        
        # Sanitize message_id for use in conversation_id
        safe_message_id = re.sub(r'[^a-zA-Z0-9_.-]', '_', message_id)


        try:
            # Log the conversation using async save_conversation
            from agentlogger.src.client import save_conversation
            await save_conversation(ConversationData(
                metadata=Metadata(
                    conversation_id=f"trigger_{safe_message_id}",
                    readable_workflow_name="Trigger Check (with Thread Context)",
                    readable_instance_context=f"{msg.from_} - {msg.subject}"
                ),
                messages=[Message(**m) for m in messages_for_llm if m.get("content") is not None]
            ))
            logger.info(f"Trigger check conversation for {message_id} logged successfully.")
        except Exception as e:
            logger.error(f"Failed to log trigger check conversation: {e}", exc_info=True)

        if not response_content or not response_content.strip():
            logger.error("LLM returned an empty or whitespace-only response.")
            return False

        try:
            response_json = json.loads(response_content)
            should_process = response_json.get("should_process")

            if isinstance(should_process, bool):
                logger.info(f"LLM trigger check parsed value: {should_process}")
                return should_process
            if isinstance(should_process, str):
                logger.info(f"LLM trigger check parsed value (from str): {should_process.lower()}")
                return should_process.lower() == 'true'
            
            logger.warning(f"Got unexpected type or value for 'should_process': {should_process}. Defaulting to False.")
            return False

        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Failed to parse JSON response from LLM: {response_content}. Error: {e}")
            return False

    except Exception as e:
        logger.error(f"Error during LLM trigger check: {e}", exc_info=True)
        return False

def main():
    """
    Main polling loop that checks for new emails and runs them against database-driven triggers.
    """
    logger.info("Trigger service started.")
    
    # On startup, run the migration to ensure the default trigger exists in the DB.
    logger.info("Running initial migration...")
    asyncio.run(migrate_to_database_triggers())
    logger.info("Initial migration complete.")

    while True:
        try:
            # Quick MCP server health check
            try: requests.get(f"http://localhost:{settings.CONTAINERPORT_MCP_IMAP}/mcp", timeout=2)
            except: continue
            
            app_settings = load_app_settings()

            if app_settings.IMAP_SERVER and app_settings.IMAP_USERNAME and app_settings.IMAP_PASSWORD:
                logger.info(f"Settings loaded for {app_settings.IMAP_USERNAME}. Checking for mail...")
                
                with MailBox(app_settings.IMAP_SERVER).login(app_settings.IMAP_USERNAME, app_settings.IMAP_PASSWORD, initial_folder='INBOX') as mailbox:
                    last_uid = get_last_uid()
                    logger.info(f"Last processed UID: {last_uid}")

                    if last_uid is None:
                        uids = mailbox.uids()
                        if uids:
                            latest_uid_on_server = uids[-1]
                            set_last_uid(latest_uid_on_server)
                            logger.info(f"No previous UID found. Baseline set to latest email UID: {latest_uid_on_server}.")
                        else:
                            logger.info("No emails found in the inbox. Will check again.")
                        time.sleep(60)
                        continue

                    messages = list(mailbox.fetch(A(uid=f'{int(last_uid) + 1}:*'), mark_seen=False))
                    filtered_messages = [msg for msg in messages if int(msg.uid) > int(last_uid)]

                    if filtered_messages:
                        logger.info(f"Found {len(filtered_messages)} new email(s).")
                        for msg in filtered_messages:
                            message_id_tuple = msg.headers.get('message-id')
                            if not message_id_tuple:
                                logger.warning(f"Skipping an email because it has no Message-ID.")
                                continue
                            message_id = message_id_tuple[0]
                            process_message(msg, message_id.strip('<>'))

                        latest_uid = filtered_messages[-1].uid
                        set_last_uid(latest_uid)
                        logger.info(f"Last processed UID updated to {latest_uid}")
                    else:
                        logger.info("No new emails.")
            else:
                logger.info("IMAP settings are not fully configured. Skipping poll cycle.")
        except Exception as e:
            logger.error(f"An unexpected error occurred in main loop: {e}. Skipping poll cycle.", exc_info=True)

        time.sleep(30)

def process_message(msg, message_id: str):
    """Process a single message with full thread context."""
    
    async def _process_with_thread_context():
        logger.info("--------------------")
        logger.info(f"New Email Received:")
        logger.info(f"  Message-ID: {message_id}")
        logger.info(f"  From: {msg.from_}")
        logger.info(f"  To: {msg.to}")
        logger.info(f"  Date: {msg.date_str}")
        logger.info(f"  Subject: {msg.subject}")
        body = msg.text or msg.html
        logger.info(f"  Body: {body[:100].strip()}...")
        logger.info("--------------------")

        # Load agent settings to get filter rules
        redis_client = get_redis_client()
        filter_rules_json = redis_client.get(RedisKeys.FILTER_RULES)
        filter_rules = FilterRules.model_validate_json(filter_rules_json) if filter_rules_json else FilterRules()

        # Check against filter rules
        if not passes_filter(msg.from_, filter_rules):
            return  # Stop processing if filters are not passed

        if not body:
            logger.info("Email has no body content. Skipping processing.")
            return

        app_settings = load_app_settings()
        trigger_conditions = redis_client.get(RedisKeys.TRIGGER_CONDITIONS)

        if not trigger_conditions:
            logger.warning("Trigger conditions not set. Skipping LLM check and agent workflow.")
            return

        # Fetch full thread context using the new imap_client
        thread_context = None
        try:
            logger.info(f"Fetching message and thread context for Message-ID: {message_id}")
            email_message = await imap_client.get_message_by_id(message_id)
            if email_message:
                thread = await imap_client.get_complete_thread(email_message)
                if thread:
                    thread_context = thread.markdown
                    logger.info(f"Successfully fetched thread context with {len(thread.messages)} messages.")
                else:
                    logger.warning("Could not fetch complete thread, using single message markdown.")
                    thread_context = f"# Email Thread\n\n## Message 1:\n\n* **From:** {email_message.from_}\n* **To:** {email_message.to}\n* **CC:** {email_message.cc}\n* **Date:** {email_message.date}\n* **Message ID:** {email_message.message_id}\n* **Subject:** {email_message.subject}\n\n{email_message.body_markdown}\n\n---\n\n"
            else:
                logger.warning(f"Could not find message with Message-ID: {message_id}. Cannot get thread context.")

        except Exception as e:
            logger.error(f"Failed to fetch thread context for {message_id}: {e}. Using single message for trigger.", exc_info=True)
            # Fallback to single message from initial fetch if client fails
            thread_context = f"SINGLE MESSAGE (No thread context available):\n\nFrom: {msg.from_}\nTo: {msg.to}\nSubject: {msg.subject}\n\n{body}"

        # Trigger check now uses thread context
        if not await passes_trigger_conditions_check(msg, trigger_conditions, app_settings, thread_context, message_id):
            logger.info("Email did not pass LLM trigger conditions check.")
            return

        # Check if draft creation is enabled
        if not app_settings.DRAFT_CREATION_ENABLED:
            logger.info("Draft creation is paused. Skipping workflow and draft creation.")
            return

        # Fetch prompts from Redis
        agent_instructions = redis_client.get(RedisKeys.AGENT_INSTRUCTIONS)
        logger.info(f"Agent instructions: {agent_instructions}")

        if not all([agent_instructions]):
            logger.warning("One or more agent settings (system prompt, user context, steps, instructions) not set in Redis. Skipping agent.")
            return

        # Run the Agent with thread context (already fetched)
        logger.info("Running agent with thread context...")
        agent = EmailAgent(
            app_settings=app_settings,
            trigger_conditions=trigger_conditions,
            agent_instructions=agent_instructions
        )
        agent_result = await agent.run(msg, message_id, thread_context)
        logger.info(f"Agent ran!")

        # Check if we should create a draft
        if agent_result and agent_result.get("success"):
            logger.info("Agent created draft successfully!")
            logger.info(agent_result["message"])
        else:
            logger.error(f"Agent failed to create draft: {agent_result.get('message', 'Unknown reason')}")

    # Run the async function
    asyncio.run(_process_with_thread_context())

if __name__ == "__main__":
    main() 
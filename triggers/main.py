import logging
import time
import requests
import asyncio
import uuid
from imap_tools import MailBox, A, MailMessage
from shared.app_settings import load_app_settings, AppSettings
from shared.redis.keys import RedisKeys
from shared.redis.redis_client import get_redis_client
from triggers.rules import passes_filter
from agent import client as agent_client
from shared.config import settings
import json
from mcp_servers.imap_mcpserver.src.utils.contextual_id import create_contextual_id
from openai import OpenAI
from agentlogger.src.client import save_conversation_sync, save_conversation
from agentlogger.src.models import ConversationData, Message, Metadata
from datetime import datetime
from triggers.migration import migrate_to_database_triggers

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

async def llm_check_passes(msg: MailMessage, trigger_conditions: str, app_settings: AppSettings, agent_name: str) -> bool:
    """
    Uses an LLM to check if the email passes the trigger conditions and logs the check.
    """
    logger.info("Performing LLM-based trigger check...")
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    trigger_conditions_with_date = trigger_conditions.replace("<<CURRENT_DATE>>", f"{current_date} (format YYYY-MM-DD)")

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
Your task is to analyze the email in the user message based on the following criteria:
---
{trigger_conditions_with_date}
---
Based on the criteria, decide if the email given by the user in the user prompt should be processed.
Respond with a single JSON object in the format: {{"should_process": true}} or {{"should_process": false}}.
"""

    user_prompt = f"""
This is the email to be processed:
UID: {msg.uid}
From: {msg.from_}
To: {", ".join(msg.to)}
Date: {msg.date_str}
Subject: {msg.subject}
Body:
{email_body[:4000]}
"""
    messages_for_llm=[
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
        messages_for_llm.append({"role": "assistant", "content": response_content})

        try:
            # We are now handling logging directly within this function.
            conversation_id = f"trigger_{uuid.uuid4()}"
            contextual_uid = create_contextual_id('INBOX', msg.uid)
            await save_conversation(ConversationData(
                metadata=Metadata(
                    conversation_id=conversation_id,
                    readable_workflow_name=f"Trigger: {agent_name}",
                    readable_instance_context=f"{msg.from_} - {msg.subject}"
                ),
                messages=[Message(**m) for m in messages_for_llm if m.get("content") is not None]
            ))
            logger.info(f"Trigger check conversation for email {contextual_uid} logged with conversation_id {conversation_id}.")
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
                        asyncio.run(process_new_messages(filtered_messages, app_settings))

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

async def process_new_messages(messages: list[MailMessage], app_settings: AppSettings):
    """
    Processes a batch of new messages against all database triggers.
    """
    all_triggers = await agent_client.list_triggers()
    if not all_triggers:
        logger.warning("No triggers found in the database. No actions will be taken.")
        return

    logger.info(f"Found {len(all_triggers)} triggers. Evaluating {len(messages)} new messages against them.")

    for msg in messages:
        contextual_uid = create_contextual_id('INBOX', msg.uid)
        logger.info(f"--- Processing Email UID: {contextual_uid} ---")
        
        for trigger in all_triggers:
            logger.info(f"Evaluating against trigger {trigger.uuid} for agent {trigger.agent_uuid}")
            
            # 1. Get the agent model for this trigger first to get its name for logging
            agent_model = await agent_client.get_agent(trigger.agent_uuid)
            if not agent_model:
                logger.error(f"Could not find agent with UUID {trigger.agent_uuid} for trigger {trigger.uuid}. Skipping.")
                continue

            # 2. Check simple filter rules
            if not passes_filter(msg.from_, trigger.filter_rules):
                logger.info(f"Email from '{msg.from_}' did not pass filter rules for trigger {trigger.uuid}. Skipping.")
                continue
            
            # 3. Check LLM-based trigger conditions
            if not await llm_check_passes(msg, trigger.trigger_conditions, app_settings, agent_model.name):
                logger.info(f"Email did not pass LLM trigger conditions for trigger {trigger.uuid}. Skipping.")
                continue
            
            logger.info(f"Email PASSED all checks for trigger {trigger.uuid}. Running agent {trigger.agent_uuid}.")
            
            # 4. Prepare and run the agent instance
            email_body = msg.text or msg.html
            input_prompt = f"Here is the email to analyze:\nUID: {contextual_uid}\nFrom: {msg.from_}\nTo: {', '.join(msg.to)}\nDate: {msg.date_str}\nSubject: {msg.subject}\nBody:\n{email_body}"

            instance_model = await agent_client.create_agent_instance(
                agent_uuid=trigger.agent_uuid,
                user_input=input_prompt,
                context_identifier=f"{msg.from_} - {msg.subject}"
            )
            
            logger.info(f"Created agent instance {instance_model.uuid} for agent {trigger.agent_uuid}")
            await agent_client.run_agent_instance(agent_model, instance_model)
            logger.info(f"Agent run for instance {instance_model.uuid} has been initiated.")

if __name__ == "__main__":
    main() 
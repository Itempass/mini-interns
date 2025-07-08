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
from mcp_servers.imap_mcpserver.src.tools.imap import find_similar_threads
from openai import OpenAI
from agentlogger.src.models import ConversationData, Message, Metadata
from datetime import datetime
import re
from uuid import uuid4
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import imap_connection, FolderNotFoundError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_last_uid(username: str):
    """Gets the last processed UID from Redis for a specific user."""
    redis_client = get_redis_client()
    uid = redis_client.get(RedisKeys.get_last_email_uid_key(username))
    return uid if uid else None

def set_last_uid(username: str, uid: str):
    """Sets the last processed UID in Redis for a specific user."""
    redis_client = get_redis_client()
    redis_client.set(RedisKeys.get_last_email_uid_key(username), uid)

async def passes_trigger_conditions_check(msg, trigger, thread_context: str, message_id: str, agent_name: str) -> bool:
    """
    Uses an LLM to check if the email passes the trigger conditions.
    Now uses full thread context for more informed trigger decisions.
    """
    logger.info("Performing LLM-based trigger check with thread context...")
    
    app_settings = load_app_settings()
    my_email = app_settings.IMAP_USERNAME or ""

    current_date = datetime.now().strftime('%Y-%m-%d')
    
    processed_conditions = trigger.trigger_conditions.replace("<<CURRENT_DATE>>", f"{current_date} (format YYYY-MM-DD)")
    processed_conditions = processed_conditions.replace("<<MY_EMAIL>>", my_email)

    if "<<TOOLRESULT:IMAP:find_similar_threads>>" in processed_conditions:
        logger.info("Found find_similar_threads tool tag in trigger conditions. Executing tool...")
        try:
            similar_threads_result = await find_similar_threads.fn(messageId=message_id)
            
            # Determine how to format the result based on its type
            if isinstance(similar_threads_result, str):
                # If it's a string (like markdown), use it directly.
                tool_result_str = similar_threads_result
            else:
                # Otherwise, assume it's a JSON-serializable object (like a dict or list).
                tool_result_str = json.dumps(similar_threads_result, indent=2)

            processed_conditions = processed_conditions.replace("<<TOOLRESULT:IMAP:find_similar_threads>>", tool_result_str)
            logger.info("Successfully executed find_similar_threads and injected result into prompt.")
        except Exception as e:
            logger.error(f"Failed to execute find_similar_threads tool: {e}", exc_info=True)
            # Fallback: replace the tag with an error message
            error_message = f"Error executing find_similar_threads: {e}"
            processed_conditions = processed_conditions.replace("<<TOOLRESULT:IMAP:find_similar_threads>>", error_message)

    if not thread_context:
        logger.warning("No thread context provided to trigger check, falling back to single message")
        email_body = msg.text or msg.html
        if not email_body:
            logger.info("Email has no body, skipping LLM trigger check and returning False.")
            return False

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )
    
    system_prompt = f"""
You are a helpful assistant that determines if an email meets a user's criteria.
Your task is to analyze the email thread in the user message based on the following criteria:
---
{processed_conditions}
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
            model=trigger.model,
            messages=messages,
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
                    conversation_id=f"trigger_check_{uuid4()}",
                    readable_workflow_name=f"Trigger Check {agent_name}",
                    readable_instance_context=f"For message: {msg.from_} - {msg.subject}",
                    model=trigger.model
                ),
                messages=[Message(**m) for m in messages if m.get("content") is not None]
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
    
    resolved_inbox_name = None

    while True:
        try:
            # Quick MCP server health check
            try: requests.get(f"http://localhost:{settings.CONTAINERPORT_MCP_IMAP}/mcp", timeout=2)
            except: 
                time.sleep(10)
                continue
            
            app_settings = load_app_settings()

            if app_settings.IMAP_SERVER and app_settings.IMAP_USERNAME and app_settings.IMAP_PASSWORD:
                # Dynamically resolve the Inbox folder name once
                if not resolved_inbox_name:
                    try:
                        logger.info("Attempting to resolve special-use folder for Inbox...")
                        with imap_connection() as (_, resolver):
                            resolved_inbox_name = resolver.get_folder_by_attribute('\\Inbox')
                        logger.info(f"Successfully resolved Inbox to: '{resolved_inbox_name}'")
                    except FolderNotFoundError:
                        logger.error("Could not resolve the Inbox folder. Trigger checking will be paused. Retrying in 1 minute.")
                        time.sleep(60)
                        continue
                    except Exception as e:
                        logger.error(f"An unexpected error occurred during Inbox resolution: {e}. Retrying in 1 minute.", exc_info=True)
                        time.sleep(60)
                        continue
                
                logger.info(f"Settings loaded for {app_settings.IMAP_USERNAME}. Checking for mail in '{resolved_inbox_name}'...")
                
                with MailBox(app_settings.IMAP_SERVER).login(app_settings.IMAP_USERNAME, app_settings.IMAP_PASSWORD, initial_folder=resolved_inbox_name) as mailbox:
                    last_uid = get_last_uid(app_settings.IMAP_USERNAME)
                    logger.info(f"Last processed UID for '{app_settings.IMAP_USERNAME}': {last_uid}")

                    if last_uid is None:
                        uids = mailbox.uids()
                        if uids:
                            latest_uid_on_server = uids[-1]
                            set_last_uid(app_settings.IMAP_USERNAME, latest_uid_on_server)
                            logger.info(f"No previous UID found for '{app_settings.IMAP_USERNAME}'. Baseline set to latest email UID: {latest_uid_on_server}.")
                        else:
                            logger.info("No emails found in the inbox. Will check again.")
                        time.sleep(60)
                        continue

                    messages = list(mailbox.fetch(A(uid=f'{int(last_uid) + 1}:*'), mark_seen=False))
                    filtered_messages = [msg for msg in messages if int(msg.uid) > int(last_uid)]

                    if filtered_messages:
                        logger.info(f"Found {len(filtered_messages)} new email(s).")
                        
                        my_email_address = app_settings.IMAP_USERNAME.lower() if app_settings.IMAP_USERNAME else ""

                        for msg in filtered_messages:
                            # ADDED: Skip emails sent by the user to avoid loops
                            if msg.from_ and my_email_address and my_email_address in msg.from_.lower():
                                logger.info(f"Skipping email sent by self: '{msg.subject}'")
                                continue

                            message_id_tuple = msg.headers.get('message-id')
                            if not message_id_tuple:
                                logger.warning(f"Skipping an email because it has no Message-ID.")
                                continue
                            message_id = message_id_tuple[0].strip('<>')
                            logger.info(f"Processing message: {message_id}")
                            process_message(msg, message_id)

                        latest_uid = filtered_messages[-1].uid
                        set_last_uid(app_settings.IMAP_USERNAME, latest_uid)
                        logger.info(f"Last processed UID for '{app_settings.IMAP_USERNAME}' updated to {latest_uid}")
                    else:
                        logger.info("No new emails.")
            else:
                logger.info("IMAP settings are not fully configured. Skipping poll cycle.")
        except Exception as e:
            logger.error(f"An unexpected error occurred in main loop: {e}. Skipping poll cycle.", exc_info=True)

        time.sleep(30)

def process_message(msg, message_id: str):
    """Process a single message against all database triggers."""
    
    async def _process_message_against_triggers():
        logger.info("--------------------")
        logger.info(f"New Email Received: Message-ID: {message_id}, From: {msg.from_}, Subject: {msg.subject}")
        body = msg.text or msg.html
        if not body:
            logger.info("Email has no body content. Skipping processing.")
            return
        
        # 1. Fetch all triggers from the database
        triggers = await agent_client.list_triggers()
        if not triggers:
            logger.info("No triggers found in the database. Skipping processing.")
            return
        logger.info(f"Found {len(triggers)} triggers in the database. Evaluating...")

        # 2. Fetch thread context once for all triggers
        thread_context = None
        try:
            logger.info(f"Fetching message and thread context for Message-ID: {message_id}")
            email_message = await imap_client.get_message_by_id(message_id)
            if email_message:
                thread = await imap_client.get_complete_thread(email_message)
                if thread:
                    thread_context = thread.markdown
                    logger.info(f"Successfully fetched thread context with {len(thread.messages)} messages.")
                else: # Fallback for single message threads
                    logger.warning("Could not fetch complete thread, using single message markdown.")
                    thread_context = f"# Email Thread\n\n## Message 1:\n\n* **From:** {email_message.from_}\n* **To:** {email_message.to}\n* **CC:** {email_message.cc}\n* **Date:** {email_message.date}\n* **Message ID:** {email_message.message_id}\n* **Subject:** {email_message.subject}\n\n{email_message.body_markdown}\n\n---\n\n"
            else:
                logger.warning(f"Could not find message with Message-ID: {message_id}. Cannot get thread context.")

        except Exception as e:
            logger.error(f"Failed to fetch thread context for {message_id}: {e}. Using single message for trigger.", exc_info=True)
            thread_context = f"SINGLE MESSAGE (No thread context available):\n\nFrom: {msg.from_}\nTo: {msg.to}\nSubject: {msg.subject}\n\n{body}"

        app_settings = load_app_settings()

        
        # 3. Iterate through each trigger
        for trigger in triggers:
            logger.info(f"Evaluating trigger '{trigger.uuid}' for agent '{trigger.agent_uuid}'")

            # 3a. Get the agent associated with the trigger
            agent_model = await agent_client.get_agent(trigger.agent_uuid)
            if not agent_model:
                logger.error(f"Agent with UUID '{trigger.agent_uuid}' not found, but trigger '{trigger.uuid}' exists. Skipping.")
                continue
            
            # 3b. Check if the agent is paused
            if agent_model.paused:
                logger.info(f"Agent '{agent_model.name}' ({agent_model.uuid}) is paused. Skipping trigger '{trigger.uuid}'.")
                continue

            # 3c. Check simple filter rules
            if not passes_filter(msg.from_, trigger.filter_rules):
                logger.info(f"Email from '{msg.from_}' did not pass filter rules for trigger '{trigger.uuid}'.")
                continue

            # 3d. Check LLM-based trigger conditions unless bypassed
            if not trigger.trigger_bypass:
                if not await passes_trigger_conditions_check(msg, trigger, thread_context, message_id, agent_model.name):
                    logger.info(f"Email did not pass LLM trigger conditions for trigger '{trigger.uuid}'.")
                    continue
            else:
                logger.info(f"Trigger '{trigger.uuid}' has LLM bypass enabled. Skipping LLM check.")


            # If all checks pass, we have a match.
            logger.info(f"SUCCESS: Email matched trigger '{trigger.uuid}'. Kicking off agent '{trigger.agent_uuid}'.")

            # The global draft creation check is now handled earlier in the main polling loop.
            
            

            # 6. Prepare user input and run the agent
            if thread_context:
                user_input = f"""
                    Here is the email thread to analyze:
                    
                    TRIGGERING MESSAGE ID: {message_id}
                    
                    FULL THREAD CONTEXT:
                    {thread_context}
                    
                    Please focus your analysis on the triggering message while considering the full conversation context. The triggering message is clearly marked in the thread above.
                """
            else: # Fallback to single message format
                user_input = f"SINGLE MESSAGE (No thread context available):\n\nFrom: {msg.from_}\nTo: {msg.to}\nSubject: {msg.subject}\n\n{body}"

            try:
                logger.info(f"Creating instance for agent '{agent_model.name}' ({agent_model.uuid})")
                instance_model = await agent_client.create_agent_instance(
                    agent_uuid=agent_model.uuid, 
                    user_input=user_input, 
                    context_identifier=f"From: {msg.from_} - Subject: {msg.subject}"
                )

                logger.info(f"Running agent instance {instance_model.uuid}")
                completed_instance = await agent_client.run_agent_instance(agent_model, instance_model)
                
                final_message = completed_instance.messages[-1] if completed_instance.messages else None
                if final_message and not final_message.tool_calls:
                    logger.info(f"Agent instance {completed_instance.uuid} completed successfully.")
                else:
                    logger.warning(f"Agent instance {completed_instance.uuid} finished with a pending tool call or no final message.")

            except Exception as e:
                logger.error(f"An error occurred while running the agent: {e}", exc_info=True)

            # Once an agent is kicked off, we continue to check other triggers.
            
        else:
            logger.info(f"No matching triggers found for email {message_id}.")
        
        logger.info("--------------------")

    # Run the async function
    asyncio.run(_process_message_against_triggers())

if __name__ == "__main__":
    main() 
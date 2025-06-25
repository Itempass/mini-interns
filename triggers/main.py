import logging
import time
import requests
import asyncio
from imap_tools import MailBox, A
from shared.app_settings import load_app_settings
from shared.redis.keys import RedisKeys
from shared.redis.redis_client import get_redis_client
from triggers.rules import passes_filter
from api.types.api_models.agent import FilterRules
from triggers.agent import EmailAgent
from shared.config import settings
import json
from mcp_servers.imap_mcpserver.src.utils.contextual_id import create_contextual_id
from mcp_servers.imap_mcpserver.src.services.imap_service import IMAPService
from shared.services.text_utils import format_email_for_display, format_thread_separator
from openai import OpenAI
from agentlogger.src.models import ConversationData, Message, Metadata
from datetime import datetime

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

async def passes_trigger_conditions_check(msg, trigger_conditions: str, app_settings, thread_context: str, contextual_uid: str) -> bool:
    """
    Uses an LLM to check if the email passes the trigger conditions.
    Now uses full thread context for more informed trigger decisions.
    """
    logger.info("Performing LLM-based trigger check with thread context...")
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    trigger_conditions = trigger_conditions.replace("<<CURRENT_DATE>>", f"{current_date} (format YYYY-MM-DD)")

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
{trigger_conditions}
---
Based on the criteria, decide if the email thread given by the user should be processed.
Consider the full conversation context when making your decision.
Respond with a single JSON object in the format: {{"should_process": true}} or {{"should_process": false}}.
"""

    if thread_context:
        user_prompt = f"""
This is the email thread to be evaluated for processing:

TRIGGERING MESSAGE UID: {contextual_uid}

{thread_context}

Please evaluate whether this email thread should be processed based on the criteria provided.
Focus on the triggering message while considering the full conversation context.
"""
    else:
        # Fallback to single message
        email_body = msg.text or msg.html
        user_prompt = f"""
This is the email to be processed (single message - no thread context available):
UID: {contextual_uid}
From: {msg.from_}
To: {msg.to}
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
        completion = client.chat.completions.create(
            model=app_settings.OPENROUTER_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1
        )

        logger.info(f"LLM trigger check response: {completion.choices[0]}")
        logger.info(f"LLM trigger check response: {completion.choices[0].message.content}")
        
        response_content = completion.choices[0].message.content
        logger.info(f"LLM trigger check raw response: '{response_content}'")
        
        messages.append({"role": "assistant", "content": response_content})

        try:
            # Log the conversation using async save_conversation
            from agentlogger.src.client import save_conversation
            await save_conversation(ConversationData(
                metadata=Metadata(
                    conversation_id=f"trigger_{contextual_uid}",
                    readable_workflow_name="Trigger Check (with Thread Context)",
                    readable_instance_context=f"{msg.from_} - {msg.subject}"
                ),
                messages=[Message(**m) for m in messages if m.get("content") is not None]
            ))
            logger.info(f"Trigger check conversation for {contextual_uid} logged successfully.")
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

def format_thread_for_agent(thread_emails, triggering_uid: str) -> str:
    """
    Format thread emails for agent consumption with clear triggering message identification.
    
    Args:
        thread_emails: List of RawEmail objects from fetch_email_thread
        triggering_uid: The contextual UID of the message that triggered the agent
        
    Returns:
        Formatted string with full thread context and clear triggering message identification
    """
    if not thread_emails:
        return "No thread context available."
    
    try:
        # Sort emails chronologically
        import dateutil.parser
        def get_date(raw_email):
            try:
                return dateutil.parser.parse(raw_email.msg['Date'])
            except (ValueError, TypeError):
                return dateutil.parser.parse("1900-01-01 00:00:00+00:00")
        
        thread_emails.sort(key=get_date)
        
        # Format each email in the thread
        formatted_messages = []
        for email in thread_emails:
            # Extract email metadata
            msg = email.msg
            subject = msg.get('Subject', '')
            from_addr = msg.get('From', '')
            to_addr = msg.get('To', '')
            cc_addr = msg.get('Cc', '')
            date = msg.get('Date', '')
            
            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get('Content-Disposition'))
                    if ctype == 'text/plain' and 'attachment' not in cdispo:
                        try:
                            charset = part.get_content_charset() or 'utf-8'
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode(charset, errors='ignore')
                                break
                        except Exception as e:
                            logger.warning(f"Could not decode body part: {e}")
                            body = "[Could not decode body]"
            else:
                try:
                    charset = msg.get_content_charset() or 'utf-8'
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(charset, errors='ignore')
                except Exception as e:
                    logger.warning(f"Could not decode body: {e}")
                    body = "[Could not decode body]"
            
            # Format this email
            formatted_email = format_email_for_display(
                subject=subject,
                from_addr=from_addr,
                to_addr=to_addr,
                cc_addr=cc_addr,
                date=date,
                body=body
            )
            
            # Mark if this is the triggering message
            if email.uid == triggering_uid:
                formatted_email = f"FULL THREAD (FIRST MESSAGE IS THE NEW MESSAGE):\n{formatted_email}"
            
            formatted_messages.append(formatted_email)
        
        # Join all messages with thread separators
        thread_context = format_thread_separator().join(formatted_messages)
        
        return f"{thread_context}"
        
    except Exception as e:
        logger.error(f"Error formatting thread for agent: {e}", exc_info=True)
        return f"Error formatting thread context: {str(e)}"

def format_single_message_for_agent(msg, contextual_uid: str) -> str:
    """
    Format a single message for agent when thread context is unavailable.
    
    Args:
        msg: imap_tools Message object
        contextual_uid: The contextual UID
        
    Returns:
        Formatted string with single message context
    """
    try:
        email_body = msg.text or msg.html or ""
        
        formatted_email = format_email_for_display(
            subject=msg.subject or '',
            from_addr=msg.from_ or '',
            to_addr=msg.to or '',
            cc_addr=msg.cc or '',
            date=msg.date_str or '',
            body=email_body
        )
        
        return f"SINGLE MESSAGE (No thread context available):\n\n{formatted_email}"
        
    except Exception as e:
        logger.error(f"Error formatting single message: {e}", exc_info=True)
        return f"Error formatting message: {str(e)}"

def main():
    """
    Polls an IMAP inbox and creates a draft for each new email.
    It will wait until settings are configured in Redis before starting.
    """
    logger.info("Trigger service started.")

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

                    # If this is the first ever run, we establish a baseline by getting the latest UID
                    # without processing any emails.
                    if last_uid is None:
                        uids = mailbox.uids()
                        if uids:
                            latest_uid_on_server = uids[-1]
                            set_last_uid(latest_uid_on_server)
                            logger.info(f"No previous UID found. Baseline set to latest email UID: {latest_uid_on_server}. Will process new emails on the next cycle.")
                        else:
                            logger.info("No emails found in the inbox. Will check again.")
                        
                        time.sleep(60) # Wait before the next poll
                        continue

                    # Due to IMAP UID range behavior with *, we need to get all messages and filter manually
                    # The issue: UID range of <value>:* always includes the highest UID even if <value> is higher
                    messages = list(mailbox.fetch(A(uid=f'{int(last_uid) + 1}:*'), mark_seen=False))
                    
                    # Filter out messages with UID <= last_uid (due to IMAP * behavior)
                    filtered_messages = [msg for msg in messages if int(msg.uid) > int(last_uid)]

                    if filtered_messages:
                        logger.info(f"Found {len(filtered_messages)} new email(s).")
                        for msg in filtered_messages:
                            contextual_uid = create_contextual_id('INBOX', msg.uid)
                            process_message(msg, contextual_uid)

                        # Update last_uid to the latest one we've processed
                        latest_uid = filtered_messages[-1].uid
                        set_last_uid(latest_uid)
                        logger.info(f"Last processed UID updated to {latest_uid}")
                    else:
                        logger.info("No new emails.")

            else:
                logger.info("IMAP settings are not fully configured in Redis. Skipping poll cycle. Will check again in 60 seconds.")

        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}. Skipping poll cycle.", exc_info=True)

        time.sleep(30)

def process_message(msg, contextual_uid: str):
    """Process a single message with full thread context."""
    
    async def _process_with_thread_context():
        logger.info("--------------------")
        logger.info(f"New Email Received:")
        logger.info(f"  UID: {contextual_uid}")
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

        # MOVED: Fetch full thread context BEFORE trigger check
        thread_context = None
        try:
            logger.info(f"Fetching thread context for trigger and agent (UID: {contextual_uid})")
            imap_service = IMAPService()
            thread_emails = await imap_service.fetch_email_thread(contextual_uid)
            if thread_emails:
                thread_context = format_thread_for_agent(thread_emails, contextual_uid)
                logger.info(f"Successfully fetched thread context with {len(thread_emails)} messages for trigger check")
            else:
                logger.warning("No thread emails found, using single message context for trigger")
                thread_context = format_single_message_for_agent(msg, contextual_uid)
        except Exception as e:
            logger.warning(f"Failed to fetch thread context: {e}. Using single message context for trigger.")
            thread_context = format_single_message_for_agent(msg, contextual_uid)

        # UPDATED: Trigger check now uses thread context
        if not await passes_trigger_conditions_check(msg, trigger_conditions, app_settings, thread_context, contextual_uid):
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
        agent_result = await agent.run(msg, contextual_uid, thread_context)
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
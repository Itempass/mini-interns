import logging
import time
from imap_tools import MailBox, A
from shared.app_settings import load_app_settings
from shared.redis.keys import RedisKeys
from shared.redis.redis_client import get_redis_client
from triggers.llm_workflow import run_workflow
from triggers.draft_handler import create_draft_reply
from triggers.rules import passes_filter
from api.types.api_models.agent import AgentSettings, FilterRules
import json

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

def main():
    """
    Polls an IMAP inbox and creates a draft for each new email.
    It will wait until settings are configured in Redis before starting.
    """
    logger.info("Trigger service started.")

    while True:
        try:
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
                            process_message(msg)

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

        time.sleep(60)

def process_message(msg):
    logger.info("--------------------")
    logger.info(f"New Email Received:")
    logger.info(f"  UID: {msg.uid}")
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
        return # Stop processing if filters are not passed

    if body:
        # Check if draft creation is enabled
        app_settings = load_app_settings()
        if not app_settings.DRAFT_CREATION_ENABLED:
            logger.info("Draft creation is paused. Skipping workflow and draft creation.")
            return
        
        # Run the LLM workflow
        workflow_result = run_workflow(msg)
        
        # Check if we should create a draft
        if workflow_result and workflow_result.get("should_create_draft"):
            logger.info("Creating draft reply...")
            draft_result = create_draft_reply(
                workflow_result["original_message"], 
                workflow_result["draft_content"]
            )
            
            if draft_result["success"]:
                logger.info("Draft created successfully!")
                logger.info(draft_result["message"])
            else:
                logger.error(f"Failed to create draft: {draft_result['message']}")
        else:
            logger.info(f"No draft created: {workflow_result.get('message', 'Unknown reason')}")
    else:
        logger.info("Email has no body content. Skipping processing.")

if __name__ == "__main__":
    main() 
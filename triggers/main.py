import logging
import time
from imap_tools import MailBox
from shared.app_settings import load_app_settings
from triggers.llm_workflow import run_workflow

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """
    Polls an IMAP inbox and creates a draft for each new email.
    It will wait until settings are configured in Redis before starting.
    """
    logger.info("Trigger service started.")
    last_uid = None

    while True:
        try:
            # Clear the cache to fetch the latest settings on each cycle
            load_app_settings.cache_clear()
            app_settings = load_app_settings()

            # Check if all required settings for this service are present
            if app_settings.IMAP_SERVER and app_settings.IMAP_USERNAME and app_settings.IMAP_PASSWORD:
                logger.info(f"Settings loaded for {app_settings.IMAP_USERNAME}. Checking for mail...")

                with MailBox(app_settings.IMAP_SERVER).login(app_settings.IMAP_USERNAME, app_settings.IMAP_PASSWORD, initial_folder='INBOX') as mailbox:
                    
                    # If last_uid is not set, this is the first successful run.
                    # Fetch existing UIDs to avoid processing all emails in the inbox.
                    if last_uid is None:
                        uids = mailbox.uids()
                        if uids:
                            last_uid = uids[-1]
                            logger.info(f"Monitoring for new emails with UID greater than {last_uid}.")
                        else:
                            logger.info("No existing emails found. Monitoring for all new emails.")

                    query = "ALL"
                    if last_uid:
                        query = f'UID {int(last_uid) + 1}:*'
                    
                    for msg in mailbox.fetch(query):
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
                        
                        # Start the LLM workflow with the email body
                        if body:
                            run_workflow(body)

                        last_uid = msg.uid
            else:
                logger.info("IMAP settings are not fully configured in Redis. Skipping poll cycle. Will check again in 60 seconds.")

        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}. Skipping poll cycle.", exc_info=True)

        # Poll every 60 seconds
        time.sleep(60)

if __name__ == "__main__":
    main() 
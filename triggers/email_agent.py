import logging
import asyncio
from imap_tools import MailMessage
from triggers.agent_helpers import run_default_agent_for_email

logger = logging.getLogger(__name__)

def process_email_with_agent(original_message: MailMessage, contextual_uid: str) -> dict:
    """
    This function serves as a backward-compatible entry point for the email trigger system.
    It utilizes the new agent framework via a helper function to process the email.
    """
    logger.info(f"Processing email with new agent framework. Contextual UID: {contextual_uid}")
    
    # The new agent framework is fully async, so we can call it directly.
    # The `run_default_agent_for_email` function now contains all the logic
    # that was previously in the EmailAgent class.
    try:
        # Since the helper is async, we need to run it in an event loop.
        # The trigger's main loop might already have one, but creating one here ensures it works standalone.
        return asyncio.run(run_default_agent_for_email(original_message, contextual_uid))
    except Exception as e:
        logger.error(f"Failed to process email using agent framework: {e}", exc_info=True)
        return {"success": False, "message": f"An unexpected error occurred during agent execution: {str(e)}"}
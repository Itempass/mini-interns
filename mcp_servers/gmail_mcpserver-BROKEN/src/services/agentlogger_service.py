import os
import httpx
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class AgentLoggerService:
    def __init__(self):
        self.base_url = os.getenv("AGENTLOGGER_BASE_URL")

    async def log_draft(
        self,
        incoming_email_id: str,
        generated_draft: str,
        account_email: str,
        draft_timestamp: Optional[datetime] = None,
    ):
        if not self.base_url:
            logger.warning("AGENTLOGGER_BASE_URL not set. Skipping draft logging.")
            return

        try:
            log_url = f"{self.base_url}/api/agentlogger/reply-logs/draft"
            params = {
                "incoming_email_id": incoming_email_id,
                "generated_draft": generated_draft,
                "account_email": account_email,
                "draft_timestamp": (draft_timestamp or datetime.now()).isoformat(),
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(log_url, params=params)

            if response.status_code == 200:
                logger.info(f"📝 Draft for {incoming_email_id} logged successfully.")
            else:
                logger.warning(
                    f"⚠️ Failed to log draft for {incoming_email_id}. Status: {response.status_code}, Response: {response.text}"
                )
        except Exception as e:
            logger.error(
                f"💥 Error logging draft for message {incoming_email_id}: {e}",
                exc_info=True,
            ) 
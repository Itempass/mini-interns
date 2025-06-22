import imaplib
import logging

from fastapi import APIRouter, HTTPException
from shared.app_settings import load_app_settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/test_imap_connection")
async def test_imap_connection():
    """
    Tests the connection to the IMAP server using settings from Redis.
    """
    try:
        settings = load_app_settings()
        if not all([settings.IMAP_SERVER, settings.IMAP_USERNAME, settings.IMAP_PASSWORD]):
            raise HTTPException(status_code=400, detail="IMAP settings are not fully configured. Please save your settings first.")

        mail = imaplib.IMAP4_SSL(settings.IMAP_SERVER)
        mail.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
        mail.logout()
        return {"message": "IMAP connection successful."}
    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP connection failed: {e}")
        raise HTTPException(status_code=400, detail=f"IMAP connection failed: {e}")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"An unexpected error occurred during IMAP connection test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}") 
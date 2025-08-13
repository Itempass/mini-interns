import imaplib
import logging

from fastapi import APIRouter, HTTPException, Depends
from shared.app_settings import load_app_settings
from user.models import User
from api.endpoints.auth import get_current_user
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import (
    imap_connection,
    IMAPConnectionError,
    acquire_imap_slot,
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/test_imap_connection")
async def test_imap_connection(current_user: User = Depends(get_current_user)):
    """
    Tests the connection to the IMAP server using settings from Redis for the current user.
    Uses the shared connection helper and per-user concurrency limiter to avoid exceeding
    provider connection limits.
    """
    try:
        app_settings = load_app_settings(user_uuid=current_user.uuid)
        if not all([app_settings.IMAP_SERVER, app_settings.IMAP_USERNAME, app_settings.IMAP_PASSWORD]):
            raise HTTPException(status_code=400, detail="IMAP settings are not fully configured. Please save your settings first.")

        # Respect per-user concurrency limits
        async with acquire_imap_slot(current_user.uuid):
            # Login/logout handled inside context manager
            with imap_connection(app_settings=app_settings) as (_mail, _resolver):
                pass
        return {"message": "IMAP connection successful."}
    except IMAPConnectionError as e:
        logger.error(f"IMAP connection failed: {e}")
        raise HTTPException(status_code=400, detail=f"IMAP connection failed: {e}")
    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP connection failed: {e}")
        raise HTTPException(status_code=400, detail=f"IMAP connection failed: {e}")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"An unexpected error occurred during IMAP connection test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
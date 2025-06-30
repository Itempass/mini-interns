import logging
from fastapi import APIRouter, HTTPException, Depends
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.app_settings import AppSettings, save_app_settings, load_app_settings
import redis

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/settings", response_model=AppSettings)
def get_all_settings():
    """
    Get all application settings, using the centralized loader.
    Sensitive values are masked.
    """
    try:
        # Use the centralized loader
        loaded_settings = load_app_settings()
        
        # Create a new model for the response, masking sensitive fields
        response_settings = AppSettings(
            IMAP_SERVER=loaded_settings.IMAP_SERVER,
            IMAP_USERNAME=loaded_settings.IMAP_USERNAME,
            OPENROUTER_MODEL=loaded_settings.OPENROUTER_MODEL,
            IMAP_PASSWORD="*****" if loaded_settings.IMAP_PASSWORD else None,
            OPENROUTER_API_KEY="*****" if loaded_settings.OPENROUTER_API_KEY else None
        )
        return response_settings
        
    except Exception as e:
        logger.error(f"Error fetching all settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/settings")
def set_all_settings(settings: AppSettings):
    """
    Set application settings. If the IMAP username is changed, reset the last email UID.
    """
    try:
        # Load the current settings to check if the username is changing
        current_settings = load_app_settings()
        
        # Check if the username exists and has changed
        if current_settings.IMAP_USERNAME and \
           current_settings.IMAP_USERNAME != settings.IMAP_USERNAME:
            logger.info(f"IMAP username changed from '{current_settings.IMAP_USERNAME}' to '{settings.IMAP_USERNAME}'. Resetting last email UID.")
            try:
                redis_client = get_redis_client()
                redis_client.delete(RedisKeys.LAST_EMAIL_UID)
                logger.info("Successfully deleted last email UID from Redis.")
            except redis.exceptions.RedisError as e:
                logger.error(f"Failed to delete last email UID from Redis: {e}", exc_info=True)
                # Optionally, decide if this should be a critical failure
                # For now, we'll log the error and continue
        
        save_app_settings(settings)
        return {"message": "Settings updated successfully"}
    except Exception as e:
        logger.error(f"Error setting settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

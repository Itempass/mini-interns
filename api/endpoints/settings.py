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
    Set application settings in Redis by calling the centralized save function.
    """
    try:
        save_app_settings(settings)
        return {"message": "Settings updated successfully"}
    except Exception as e:
        logger.error(f"Error setting settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

import logging
import json
from fastapi import APIRouter, HTTPException, Depends, Body
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.app_settings import AppSettings, save_app_settings, load_app_settings
import redis
from typing import Dict, Any, List
from shared.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

def get_embedding_models_with_key_status() -> List[Dict[str, Any]]:
    """
    Loads embedding models from the JSON file and checks if the required API keys are present.
    """
    try:
        with open("shared/embedding_models.json", "r") as f:
            models = json.load(f)
    except FileNotFoundError:
        return []

    # Map providers to their corresponding API key in the config
    provider_key_map = {
        "openai": settings.EMBEDDING_OPENAI_API_KEY,
        "voyage": settings.EMBEDDING_VOYAGE_API_KEY,
    }

    models_with_status = []
    for model_name, model_info in models.items():
        provider = model_info.get("provider")
        api_key = provider_key_map.get(provider)
        
        # We need a new dictionary to add the model_name to it
        model_data = model_info.copy()
        model_data["model_name_from_key"] = model_name
        model_data["api_key_provided"] = bool(api_key and api_key != "EDIT-ME")
        models_with_status.append(model_data)
        
    return models_with_status

@router.get("/settings")
async def get_settings():
    """
    Retrieves all application settings and available embedding models.
    """
    current_settings = load_app_settings()
    embedding_models = get_embedding_models_with_key_status()
    
    return {
        "settings": current_settings.dict(),
        "embedding_models": embedding_models
    }

@router.post("/settings")
async def set_settings(app_settings: AppSettings = Body(...)):
    """
    Updates one or more application settings.
    If the IMAP server or username changes, the last processed email UID is reset.
    """
    try:
        # If a username is provided in the update, always reset the UID for that account.
        # This ensures that re-saving settings for an account starts its sync from scratch.
        if app_settings.IMAP_USERNAME:
            logger.info(f"Settings contain a username ('{app_settings.IMAP_USERNAME}'). Resetting its last processed email UID.")
            redis_client = get_redis_client()
            namespaced_uid_key = RedisKeys.get_last_email_uid_key(app_settings.IMAP_USERNAME)
            redis_client.delete(namespaced_uid_key)

        save_app_settings(app_settings)
        return {"status": "success", "message": "Settings updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/settings/tone-of-voice")
async def get_tone_of_voice_profile():
    """
    Retrieves the stored tone of voice profile from Redis.
    """
    try:
        redis_client = get_redis_client()
        profile_json = redis_client.get(RedisKeys.TONE_OF_VOICE_PROFILE)
        
        if profile_json:
            return json.loads(profile_json)
            
        # If no profile is found, return an empty object
        return {}
    except Exception as e:
        logger.error(f"Error fetching tone of voice profile from Redis: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tone of voice profile.")

@router.get("/settings/tone-of-voice/status")
async def get_tone_of_voice_status(redis_client: redis.Redis = Depends(get_redis_client)):
    """
    Retrieves the current status of the tone of voice analysis task.
    If the status key is missing, it checks for a saved profile as a fallback.
    """
    try:
        status = redis_client.get(RedisKeys.TONE_OF_VOICE_STATUS)
        if status:
            return {"status": status}

        # Fallback: If no status, check if a profile exists.
        # This handles cases where the server restarted after completion.
        if redis_client.exists(RedisKeys.TONE_OF_VOICE_PROFILE):
            return {"status": "completed"}
            
        return {"status": "not_started"}
    except Exception as e:
        logger.error(f"Error fetching tone of voice status from Redis: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tone of voice status.")

import logging
import json
from fastapi import APIRouter, HTTPException, Depends, Body
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.app_settings import AppSettings, save_app_settings, load_app_settings
import redis
from typing import Dict, Any, List
from shared.config import settings
from user.models import User
from api.endpoints.auth import get_current_user
from shared.qdrant.qdrant_client import recreate_collection

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
async def get_settings(current_user: User = Depends(get_current_user)):
    """
    Retrieves all application settings for the current user and available embedding models.
    """
    current_settings = load_app_settings(user_uuid=current_user.uuid)
    embedding_models = get_embedding_models_with_key_status()
    
    return {
        "settings": current_settings.dict(),
        "embedding_models": embedding_models
    }

@router.post("/settings")
async def set_settings(app_settings: AppSettings = Body(...), current_user: User = Depends(get_current_user)):
    """
    Updates one or more application settings for the current user.
    If the embedding model is changed, the user's Qdrant collection is recreated.
    """
    try:
        # Check if the embedding model is being changed
        if app_settings.EMBEDDING_MODEL:
            current_settings = load_app_settings(user_uuid=current_user.uuid)
            if current_settings.EMBEDDING_MODEL != app_settings.EMBEDDING_MODEL:
                logger.warning(f"Embedding model changed for user {current_user.uuid}. Recreating Qdrant collection.")
                recreate_collection(user_uuid=current_user.uuid)

        save_app_settings(app_settings, user_uuid=current_user.uuid)
        return {"status": "success", "message": "Settings updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/settings/tone-of-voice")
async def get_tone_of_voice_profile(current_user: User = Depends(get_current_user)):
    """
    Retrieves the stored tone of voice profile from Redis for the current user.
    """
    try:
        redis_client = get_redis_client()
        profile_key = RedisKeys.get_tone_of_voice_profile_key(current_user.uuid)
        profile_json = redis_client.get(profile_key)
        
        if profile_json:
            return json.loads(profile_json)
            
        # If no profile is found, return an empty object
        return {}
    except Exception as e:
        logger.error(f"Error fetching tone of voice profile from Redis for user {current_user.uuid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tone of voice profile.")

@router.get("/settings/tone-of-voice/status")
async def get_tone_of_voice_status(current_user: User = Depends(get_current_user)):
    """
    Retrieves the current status of the tone of voice analysis task for the current user.
    """
    try:
        redis_client = get_redis_client()
        status_key = RedisKeys.get_tone_of_voice_status_key(current_user.uuid)
        status = redis_client.get(status_key)
        
        if status:
            return {"status": status}

        # Fallback for completed status
        profile_key = RedisKeys.get_tone_of_voice_profile_key(current_user.uuid)
        if redis_client.exists(profile_key):
            return {"status": "completed"}
            
        return {"status": "not_started"}
    except Exception as e:
        logger.error(f"Error fetching tone of voice status from Redis for user {current_user.uuid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tone of voice status.")

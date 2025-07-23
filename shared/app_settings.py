import logging
import json
from functools import lru_cache
from pydantic import BaseModel, model_validator
from typing import Optional, Dict, Any
from uuid import UUID

from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.security.encryption import encrypt_value, decrypt_value
from shared.config import settings

logger = logging.getLogger(__name__)

def _find_best_available_model() -> Optional[str]:
    """
    Determines the best available embedding model based on defaults and available API keys.
    This logic is centralized here to be used for setting initial defaults for new users.
    """
    try:
        with open("shared/embedding_models.json", "r") as f:
            models = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error("Could not load or parse embedding_models.json.")
        return None

    provider_key_map = {
        "openai": settings.EMBEDDING_OPENAI_API_KEY,
        "voyage": settings.EMBEDDING_VOYAGE_API_KEY,
    }

    # First, try to find the model marked as default
    for model_key, model_info in models.items():
        if model_info.get("default"):
            provider = model_info.get("provider")
            api_key = provider_key_map.get(provider)
            if provider and api_key and api_key != "EDIT-ME":
                logger.info(f"Default model '{model_key}' is available. Using it as the initial setting.")
                return model_key
            else:
                logger.warning(f"Default model '{model_key}' is specified, but its API key is not configured.")
                break

    # If the default is not available, find the first available model
    for model_key, model_info in models.items():
        provider = model_info.get("provider")
        api_key = provider_key_map.get(provider)
        if provider and api_key and api_key != "EDIT-ME":
            logger.info(f"Found first available model '{model_key}' to use as the initial setting.")
            return model_key

    logger.warning("No embedding models have a configured API key. Cannot set an initial model.")
    return None

class AppSettings(BaseModel):
    """
    A Pydantic model for application settings, used for API communication
    and service configuration. Fields are optional to allow for partial updates
    and graceful startup.
    """
    IMAP_SERVER: Optional[str] = None
    IMAP_USERNAME: Optional[str] = None
    IMAP_PASSWORD: Optional[str] = None
    EMBEDDING_MODEL: Optional[str] = None

    @model_validator(mode='after')
    def set_default_embedding_model(self) -> 'AppSettings':
        """
        If no embedding model is set, try to determine and set a default one.
        This ensures that new users get a sensible default configuration.
        """
        if self.EMBEDDING_MODEL is None:
            self.EMBEDDING_MODEL = _find_best_available_model()
        return self

def load_app_settings(user_uuid: Optional[UUID] = None) -> AppSettings:
    """
    Loads all application settings from Redis and decrypts sensitive values.
    If a user_uuid is provided, it fetches user-specific settings.
    If an embedding model is not set for the user, it determines a default,
    saves it back to Redis, and then returns the updated settings.
    """
    logger.info(f"Loading application settings from Redis for user: {user_uuid or 'global'}")
    redis_client = get_redis_client()
    
    keys_to_fetch = []
    if user_uuid:
        keys_to_fetch = [
            RedisKeys.get_imap_server_key(user_uuid),
            RedisKeys.get_imap_username_key(user_uuid),
            RedisKeys.get_imap_password_key(user_uuid),
            RedisKeys.get_embedding_model_key(user_uuid)
        ]
    else:
        # Fallback for legacy single-user mode
        keys_to_fetch = [
            "settings:imap_server",
            "settings:imap_username",
            "settings:imap_password",
            "settings:embedding_model"
        ]

    pipeline = redis_client.pipeline()
    pipeline.mget(keys_to_fetch)
    results = pipeline.execute()[0]

    settings_data = {
        "IMAP_SERVER": results[0],
        "IMAP_USERNAME": results[1],
        "IMAP_PASSWORD": results[2],
        "EMBEDDING_MODEL": results[3]
    }
    
    # Decrypt sensitive fields if they exist
    try:
        if settings_data.get("IMAP_PASSWORD"):
            logger.info(f"Value from Redis to be decrypted (IMAP_PASSWORD): {settings_data['IMAP_PASSWORD']}")
            settings_data["IMAP_PASSWORD"] = decrypt_value(settings_data["IMAP_PASSWORD"])
    except Exception as e:
        logger.error(f"An unexpected error occurred during settings decryption: {e}", exc_info=True)

    # Instantiate the Pydantic model. This will trigger the validator to set a default if needed.
    settings_model = AppSettings(**settings_data)

    # If a default was just set by the validator, persist it back to Redis for this user.
    if settings_data["EMBEDDING_MODEL"] is None and settings_model.EMBEDDING_MODEL is not None and user_uuid:
        logger.info(f"No embedding model was set for user {user_uuid}. Saving default: {settings_model.EMBEDDING_MODEL}")
        save_app_settings(AppSettings(EMBEDDING_MODEL=settings_model.EMBEDDING_MODEL), user_uuid=user_uuid)

    return settings_model

def save_app_settings(settings: AppSettings, user_uuid: Optional[UUID] = None):
    """
    Saves application settings to Redis, encrypting sensitive values.
    If a user_uuid is provided, it saves settings for that specific user.
    Otherwise, it falls back to the legacy global keys.
    """
    logger.info(f"Saving application settings to Redis for user: {user_uuid or 'global'}")
    redis_client = get_redis_client()

    pipeline = redis_client.pipeline()
    update_count = 0

    for field, value in settings.dict(exclude_unset=True).items():
        redis_key = None
        if user_uuid:
            if field == "IMAP_SERVER":
                redis_key = RedisKeys.get_imap_server_key(user_uuid)
            elif field == "IMAP_USERNAME":
                redis_key = RedisKeys.get_imap_username_key(user_uuid)
            elif field == "IMAP_PASSWORD":
                redis_key = RedisKeys.get_imap_password_key(user_uuid)
            elif field == "EMBEDDING_MODEL":
                redis_key = RedisKeys.get_embedding_model_key(user_uuid)
        else:
            # Fallback for legacy single-user mode
            legacy_key_map = {
                "IMAP_SERVER": "settings:imap_server",
                "IMAP_USERNAME": "settings:imap_username",
                "IMAP_PASSWORD": "settings:imap_password",
                "EMBEDDING_MODEL": "settings:embedding_model"
            }
            redis_key = legacy_key_map.get(field)

        if not redis_key:
            continue

        # For sensitive fields, don't save the placeholder value
        if field in ["IMAP_PASSWORD"] and value == "*****":
            continue

        if value is not None:
            # Encrypt sensitive fields before saving
            if field in ["IMAP_PASSWORD"]:
                logger.info(f"Value to be encrypted ({field}): '{value}'")
                encrypted_value = encrypt_value(value)
                logger.info(f"Encrypted value ({field}): '{encrypted_value}'")
                value = encrypted_value

            # Convert boolean to string for Redis storage
            if isinstance(value, bool):
                value = str(value).lower()
            pipeline.set(redis_key, value)
            update_count += 1
    
    if update_count > 0:
        pipeline.execute()
        logger.info(f"Successfully updated {update_count} settings in Redis.")
    else:
        logger.info("No settings were updated.") 
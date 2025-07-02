import logging
from functools import lru_cache
from pydantic import BaseModel
from typing import Optional

from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.security.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)

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

def load_app_settings() -> AppSettings:
    """
    Loads all application settings from Redis and decrypts sensitive values.
    This function does not validate, it simply returns the current state from Redis.
    """
    logger.info("Loading application settings from Redis...")
    redis_client = get_redis_client()
    
    pipeline = redis_client.pipeline()
    pipeline.mget(
        RedisKeys.IMAP_SERVER,
        RedisKeys.IMAP_USERNAME,
        RedisKeys.IMAP_PASSWORD,
        RedisKeys.EMBEDDING_MODEL
    )
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

    return AppSettings(**settings_data)

def save_app_settings(settings: AppSettings):
    """
    Saves application settings to Redis, encrypting sensitive values.
    This function uses a mapping to dynamically update settings, making it
    concise and easy to extend.
    """
    logger.info("Saving application settings to Redis...")
    redis_client = get_redis_client()

    KEY_MAP = {
        "IMAP_SERVER": RedisKeys.IMAP_SERVER,
        "IMAP_USERNAME": RedisKeys.IMAP_USERNAME,
        "IMAP_PASSWORD": RedisKeys.IMAP_PASSWORD,
        "EMBEDDING_MODEL": RedisKeys.EMBEDDING_MODEL,
    }

    pipeline = redis_client.pipeline()
    update_count = 0

    for field, value in settings.dict(exclude_unset=True).items():
        redis_key = KEY_MAP.get(field)
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
import logging
from functools import lru_cache
from pydantic import BaseModel
from typing import Optional

from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys

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
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: Optional[str] = None

@lru_cache(maxsize=1)
def load_app_settings() -> AppSettings:
    """
    Loads all application settings from Redis. This function does not validate,
    it simply returns the current state from Redis.
    """
    logger.info("Loading application settings from Redis...")
    redis_client = get_redis_client()
    
    pipeline = redis_client.pipeline()
    pipeline.mget(
        RedisKeys.IMAP_SERVER,
        RedisKeys.IMAP_USERNAME,
        RedisKeys.IMAP_PASSWORD,
        RedisKeys.OPENROUTER_API_KEY,
        RedisKeys.OPENROUTER_MODEL
    )
    results = pipeline.execute()[0]

    settings_data = {
        "IMAP_SERVER": results[0],
        "IMAP_USERNAME": results[1],
        "IMAP_PASSWORD": results[2],
        "OPENROUTER_API_KEY": results[3],
        "OPENROUTER_MODEL": results[4]
    }
    
    return AppSettings(**settings_data)

def save_app_settings(settings: AppSettings):
    """
    Saves application settings to Redis.
    This function uses a mapping to dynamically update settings, making it
    concise and easy to extend.
    """
    logger.info("Saving application settings to Redis...")
    redis_client = get_redis_client()

    KEY_MAP = {
        "IMAP_SERVER": RedisKeys.IMAP_SERVER,
        "IMAP_USERNAME": RedisKeys.IMAP_USERNAME,
        "IMAP_PASSWORD": RedisKeys.IMAP_PASSWORD,
        "OPENROUTER_API_KEY": RedisKeys.OPENROUTER_API_KEY,
        "OPENROUTER_MODEL": RedisKeys.OPENROUTER_MODEL,
    }

    pipeline = redis_client.pipeline()
    update_count = 0

    for field, value in settings.dict(exclude_unset=True).items():
        redis_key = KEY_MAP.get(field)
        if not redis_key:
            continue

        # For sensitive fields, don't save the placeholder value
        if field in ["IMAP_PASSWORD", "OPENROUTER_API_KEY"] and value == "*****":
            continue

        if value is not None:
            pipeline.set(redis_key, value)
            update_count += 1
    
    if update_count > 0:
        pipeline.execute()
        logger.info(f"Successfully updated {update_count} settings in Redis.")
    else:
        logger.info("No settings were updated.") 
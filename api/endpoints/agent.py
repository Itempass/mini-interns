import logging
import json
from fastapi import APIRouter, HTTPException
from functools import lru_cache
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from api.types.api_models.agent import AgentSettings, FilterRules

router = APIRouter()
logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_default_system_prompt():
    """
    Loads the default system prompt from a file.
    Caches the result to avoid repeated file I/O.
    """
    try:
        # Assuming the app runs from the project root
        with open("api/defaults/systemprompt_default.md", "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("default system prompt file not found. Using a fallback default.")
        raise Exception("default system prompt file not found")

@lru_cache(maxsize=1)
def get_default_trigger_conditions():
    """
    Loads the default trigger conditions from a file.
    Caches the result to avoid repeated file I/O.
    """
    try:
        with open("api/defaults/triggerconditions_default.md", "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("default trigger conditions file not found. Using a fallback default.")
        raise Exception("default trigger conditions file not found")

@router.get("/agent/settings", response_model=AgentSettings)
def get_agent_settings():
    """
    Get agent settings from Redis.
    """
    try:
        redis_client = get_redis_client()
        pipeline = redis_client.pipeline()
        pipeline.mget(
            RedisKeys.SYSTEM_PROMPT,
            RedisKeys.TRIGGER_CONDITIONS,
            RedisKeys.USER_CONTEXT,
            RedisKeys.FILTER_RULES
        )
        results = pipeline.execute()[0]
        
        filter_rules_json = results[3]
        filter_rules = FilterRules.model_validate_json(filter_rules_json) if filter_rules_json else FilterRules()

        settings = AgentSettings(
            system_prompt=results[0] or get_default_system_prompt(),
            trigger_conditions=results[1] or get_default_trigger_conditions(),
            user_context=results[2],
            filter_rules=filter_rules
        )
        return settings
    except Exception as e:
        logger.error(f"Error fetching agent settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/agent/settings")
def set_agent_settings(settings: AgentSettings):
    """
    Set agent settings in Redis.
    """
    try:
        redis_client = get_redis_client()
        pipeline = redis_client.pipeline()
        
        if settings.system_prompt is not None:
            pipeline.set(RedisKeys.SYSTEM_PROMPT, settings.system_prompt)
        if settings.trigger_conditions is not None:
            pipeline.set(RedisKeys.TRIGGER_CONDITIONS, settings.trigger_conditions)
        if settings.user_context is not None:
            pipeline.set(RedisKeys.USER_CONTEXT, settings.user_context)
        if settings.filter_rules is not None:
            pipeline.set(RedisKeys.FILTER_RULES, settings.filter_rules.json())
            
        pipeline.execute()
        return {"message": "Agent settings updated successfully"}
    except Exception as e:
        logger.error(f"Error setting agent settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

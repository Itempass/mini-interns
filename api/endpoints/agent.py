import logging
from fastapi import APIRouter, HTTPException
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from api.types.api_models.agent import AgentSettings

router = APIRouter()
logger = logging.getLogger(__name__)

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
            RedisKeys.USER_CONTEXT
        )
        results = pipeline.execute()[0]
        
        settings = AgentSettings(
            system_prompt=results[0],
            trigger_conditions=results[1],
            user_context=results[2]
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
            
        pipeline.execute()
        return {"message": "Agent settings updated successfully"}
    except Exception as e:
        logger.error(f"Error setting agent settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

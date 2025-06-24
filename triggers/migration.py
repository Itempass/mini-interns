import logging
import json

from agent import client as agent_client
from shared.redis.keys import RedisKeys
from shared.redis.redis_client import get_redis_client
from triggers.agent_helpers import get_or_create_default_agent_id

logger = logging.getLogger(__name__)

async def migrate_to_database_triggers():
    """
    Ensures the default Redis-configured trigger is migrated to the database.
    This function is idempotent and safe to run on every startup.
    """
    logger.info("--- Starting trigger migration check ---")
    try:
        # 1. Get or create the default agent ID. This ensures an agent exists.
        default_agent_id = await get_or_create_default_agent_id()
        logger.info(f"Default agent ID: {default_agent_id}")

        # 2. Check if a trigger for this agent already exists in the database.
        existing_trigger = await agent_client.get_trigger_for_agent(default_agent_id)

        if existing_trigger:
            logger.info(f"Trigger for agent {default_agent_id} already exists. Migration not needed.")
            logger.info("--- Trigger migration check complete ---")
            return

        # 3. If no trigger exists, migrate the settings from Redis.
        logger.info(f"No trigger found for agent {default_agent_id}. Migrating from Redis...")
        redis_client = get_redis_client()

        # Fetch trigger conditions from Redis
        trigger_conditions = redis_client.get(RedisKeys.TRIGGER_CONDITIONS) or ""
        if not trigger_conditions:
            logger.warning("TRIGGER_CONDITIONS not found in Redis. Creating trigger with empty conditions.")

        # Fetch filter rules from Redis
        filter_rules_json = redis_client.get(RedisKeys.FILTER_RULES)
        filter_rules = json.loads(filter_rules_json) if filter_rules_json else {}
        if not filter_rules:
            logger.warning("FILTER_RULES not found in Redis. Creating trigger with empty filters.")

        # Create the trigger in the database
        await agent_client.create_trigger(
            agent_uuid=default_agent_id,
            trigger_conditions=trigger_conditions,
            filter_rules=filter_rules,
        )

        logger.info(f"Successfully created trigger for agent {default_agent_id} in the database.")
        
    except Exception as e:
        logger.error(f"An error occurred during trigger migration: {e}", exc_info=True)
        # Stop the application from starting in a bad state
        raise
    
    logger.info("--- Trigger migration check complete ---") 
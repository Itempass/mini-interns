import logging
from uuid import UUID
from agent import client as agent_client
from shared.redis.keys import RedisKeys
from shared.redis.redis_client import get_redis_client

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """
You are an agent that should follow the user instructions and execute tasks, using the tools provided to you.
The user will provide you with instructions on what to do. Follow these dilligently.
"""

async def get_or_create_default_agent_id() -> UUID:
    """
    Retrieves the default agent ID from Redis. If it doesn't exist or is invalid, 
    it creates a new default agent, stores its ID in Redis, and returns the new ID.
    """
    redis_client = get_redis_client()
    agent_id_str = redis_client.get(RedisKeys.DEFAULT_AGENT_ID)

    if agent_id_str:
        logger.info(f"Found potential default agent ID in Redis: {agent_id_str}")
        agent_id = UUID(agent_id_str)
        # Verify the agent actually exists in the database
        agent_model = await agent_client.get_agent(agent_id)
        if agent_model:
            logger.info(f"Verified agent {agent_id} exists. Using it.")
            return agent_id
        else:
            logger.warning(f"Orphaned agent ID {agent_id} found in Redis. The agent does not exist in the DB. Deleting key and creating a new agent.")
            redis_client.delete(RedisKeys.DEFAULT_AGENT_ID)

    logger.info("No valid default agent ID found. Creating a new one.")
    
    # Fetch user instructions from Redis to create the agent
    user_instructions = redis_client.get(RedisKeys.AGENT_INSTRUCTIONS)
    if not user_instructions:
        # Fallback if not set in Redis, to prevent failure
        user_instructions = "Analyze the provided email and take appropriate action based on its content."
        logger.warning(f"AGENT_INSTRUCTIONS not found in Redis. Using a fallback.")

    # Create the agent
    agent_model = await agent_client.create_agent(
        name="Default Email Agent",
        description="The default agent used by the email trigger system.",
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_instructions=user_instructions,
    )

    # Store the new agent's ID in Redis
    agent_id = agent_model.uuid
    redis_client.set(RedisKeys.DEFAULT_AGENT_ID, str(agent_id))
    logger.info(f"Created new default agent and stored its ID in Redis: {agent_id}")

    return agent_id 
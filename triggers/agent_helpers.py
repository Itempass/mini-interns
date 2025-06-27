import logging
from uuid import UUID
from agent import client as agent_client
from shared.redis.keys import RedisKeys
from shared.redis.redis_client import get_redis_client
import json

# Import the necessary models
from agent.models import AgentModel, AgentInstanceModel
from imap_tools import MailMessage

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

    # Fetch tool settings from Redis
    agent_tools_json = redis_client.get(RedisKeys.AGENT_TOOLS)
    agent_tools = json.loads(agent_tools_json) if agent_tools_json else {}
    if not agent_tools:
        logger.warning("AGENT_TOOLS not found in Redis. Agent will be created with no tools.")

    # Create the agent
    agent_model = await agent_client.create_agent(
        name="Default Email Agent",
        description="The default agent used by the email trigger system.",
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_instructions=user_instructions,
        tools=agent_tools,
    )

    # Store the new agent's ID in Redis
    agent_id = agent_model.uuid
    redis_client.set(RedisKeys.DEFAULT_AGENT_ID, str(agent_id))
    logger.info(f"Created new default agent and stored its ID in Redis: {agent_id}")

    return agent_id


async def run_default_agent_for_email(original_message: MailMessage, contextual_uid: str) -> dict:
    """
    Runs the default agent for a given email message.
    This function orchestrates getting the agent, creating an instance, running it,
    and returning a response compatible with the trigger system.
    """
    logger.info(f"Running default agent for email with contextual_uid: {contextual_uid}")

    try:
        # 1. Get the default agent ID and model
        agent_id = await get_or_create_default_agent_id()
        agent_model = await agent_client.get_agent(agent_id)
        if not agent_model:
            error_msg = f"Failed to retrieve agent model for default agent ID: {agent_id}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg}

        # 2. Extract email content and create the instance
        email_body = original_message.text or original_message.html
        if not email_body:
            logger.warning("Email has no body content.")
            return {"success": False, "message": "Email has no body content."}

        input_prompt = f"""
            Here is the email to analyze:
            UID: {contextual_uid}
            From: {original_message.from_}
            To: {', '.join(original_message.to)}
            Date: {original_message.date_str}
            Subject: {original_message.subject}
            Body:
            {email_body}
        """

        instance_model = await agent_client.create_agent_instance(
            agent_uuid=agent_id,
            user_input=input_prompt,
            context_identifier=f"{original_message.from_} - {original_message.subject}"
        )
        logger.info(f"Created agent instance {instance_model.uuid} for agent {agent_id}")

        # 3. Run the agent instance
        completed_instance = await agent_client.run_agent_instance(agent_model, instance_model)
        logger.info(f"Completed run for instance {instance_model.uuid}")

        # 4. Format and return the response
        final_message = completed_instance.messages[-1] if completed_instance.messages else None
        if final_message and final_message.role == "assistant" and final_message.content:
            return {"success": True, "message": f"Agent finished: {final_message.content}"}
        elif final_message and final_message.tool_calls:
             return {"success": False, "message": "Agent finished with a tool call, but further action is required."}
        else:
            # Fallback in case the final message is not as expected
            logger.warning(f"Agent instance {completed_instance.uuid} finished without a conclusive final message.")
            return {"success": False, "message": "Agent did not produce a final response."}

    except Exception as e:
        logger.error(f"An error occurred while running the default agent: {e}", exc_info=True)
        return {"success": False, "message": f"An unexpected error occurred: {str(e)}"} 
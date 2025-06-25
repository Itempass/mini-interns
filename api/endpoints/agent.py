import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from functools import lru_cache
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.qdrant.qdrant_client import count_points
from api.types.api_models.agent import AgentSettings, FilterRules
from api.background_tasks.inbox_initializer import initialize_inbox
import json
from uuid import UUID
from typing import List
import asyncio

from agent import client as agent_client
from agent.models import AgentModel, TriggerModel
from api.types.api_models.single_agent import AgentWithTriggerSettings, CreateAgentRequest

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
            RedisKeys.TRIGGER_CONDITIONS,
            RedisKeys.FILTER_RULES,
            RedisKeys.AGENT_INSTRUCTIONS,
            RedisKeys.AGENT_TOOLS
        )
        results = pipeline.execute()[0]
        
        trigger_conditions = results[0]
        filter_rules_json = results[1]
        agent_instructions = results[2]
        agent_tools_json = results[3]
        
        filter_rules = FilterRules.model_validate_json(filter_rules_json) if filter_rules_json else FilterRules()
        agent_tools = json.loads(agent_tools_json) if agent_tools_json else {}

        settings = AgentSettings(
            trigger_conditions=trigger_conditions,
            filter_rules=filter_rules,
            agent_instructions=agent_instructions,
            agent_tools=agent_tools
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
        
        if settings.trigger_conditions is not None:
            pipeline.set(RedisKeys.TRIGGER_CONDITIONS, settings.trigger_conditions)
        if settings.filter_rules is not None:
            pipeline.set(RedisKeys.FILTER_RULES, settings.filter_rules.json())
        if settings.agent_instructions is not None:
            pipeline.set(RedisKeys.AGENT_INSTRUCTIONS, settings.agent_instructions)
        if settings.agent_tools is not None:
            pipeline.set(RedisKeys.AGENT_TOOLS, json.dumps(settings.agent_tools))
            
        pipeline.execute()
        return {"message": "Agent settings updated successfully"}
    except Exception as e:
        logger.error(f"Error setting agent settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/agent/initialize-inbox")
async def trigger_inbox_initialization(background_tasks: BackgroundTasks):
    """
    Triggers the background task to initialize the user's inbox.
    Uses Redis to track the status and prevent multiple initializations.
    """
    redis_client = get_redis_client()
    status = redis_client.get(RedisKeys.INBOX_INITIALIZATION_STATUS)

    if status == "running":
        return {"message": "Inbox initialization is already in progress."}
    
    # Also check the fallback condition to prevent re-running a completed task
    if status == "completed" or count_points(collection_name="emails") > 0:
        return {"message": "Inbox has already been initialized."}

    # Set the status to "running" immediately to prevent race conditions
    redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "running")

    # The background task will update the status upon completion or failure
    background_tasks.add_task(initialize_inbox)
    return {"message": "Inbox initialization started."}

@router.get("/agent/initialize-inbox/status")
async def get_inbox_initialization_status():
    """
    Gets the status of the inbox initialization task from Redis.
    Falls back to checking Qdrant if the Redis key is not present.
    """
    try:
        redis_client = get_redis_client()
        status = redis_client.get(RedisKeys.INBOX_INITIALIZATION_STATUS)

        if status:
            return {"status": status}

        # If no status is in Redis, check Qdrant as a fallback.
        # This handles the case where the server restarted after completion.
        if count_points(collection_name="emails") > 0:
            return {"status": "completed"}

        return {"status": "not_started"}
    except Exception as e:
        logger.error(f"Error fetching inbox initialization status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/agents", response_model=List[AgentWithTriggerSettings])
async def list_agents():
    """
    Lists all available agents from the database, including their trigger settings.
    """
    logger.info("GET /agents - Listing all agents with trigger settings")
    try:
        agents = await agent_client.list_agents()
        
        async def enrich_agent_with_trigger(agent: AgentModel) -> AgentWithTriggerSettings:
            trigger = await agent_client.get_trigger_for_agent(agent.uuid)
            if not trigger:
                trigger_settings = {
                    "trigger_conditions": get_default_trigger_conditions(),
                    "filter_rules": FilterRules()
                }
            else:
                trigger_settings = {
                    "trigger_conditions": trigger.trigger_conditions,
                    "filter_rules": FilterRules.model_validate(trigger.filter_rules) if trigger.filter_rules else FilterRules()
                }
            
            response_data = agent.model_dump()
            response_data.update(trigger_settings)
            return AgentWithTriggerSettings.model_validate(response_data)

        enriched_agents = await asyncio.gather(*[enrich_agent_with_trigger(agent) for agent in agents])

        logger.info(f"GET /agents - Found {len(enriched_agents)} agents with trigger settings.")
        return enriched_agents
    except Exception as e:
        logger.error(f"GET /agents - Error listing agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error listing agents.")

@router.get("/agents/{agent_uuid}", response_model=AgentWithTriggerSettings)
async def get_agent(agent_uuid: UUID):
    """
    Retrieves a specific agent by its UUID, including its trigger settings.
    """
    logger.info(f"GET /agents/{agent_uuid} - Retrieving agent with trigger settings")
    try:
        agent = await agent_client.get_agent(agent_uuid)
        if not agent:
            logger.warning(f"GET /agents/{agent_uuid} - Agent not found")
            raise HTTPException(status_code=404, detail="Agent not found")

        trigger = await agent_client.get_trigger_for_agent(agent_uuid)
        if not trigger:
            # Create a default trigger settings response if none exists
            trigger_settings = {
                "trigger_conditions": get_default_trigger_conditions(),
                "filter_rules": FilterRules()
            }
        else:
            trigger_settings = {
                "trigger_conditions": trigger.trigger_conditions,
                "filter_rules": FilterRules.model_validate(trigger.filter_rules) if trigger.filter_rules else FilterRules()
            }

        response_data = agent.model_dump()
        response_data.update(trigger_settings)
        
        response = AgentWithTriggerSettings.model_validate(response_data)
        logger.info(f"GET /agents/{agent_uuid} - Agent with trigger settings retrieved successfully")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GET /agents/{agent_uuid} - Error retrieving agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving agent.")

@router.put("/agents/{agent_uuid}", response_model=AgentWithTriggerSettings)
async def update_agent(agent_uuid: UUID, agent_update: AgentWithTriggerSettings):
    """
    Updates a specific agent and its trigger settings.
    """
    logger.info(f"PUT /agents/{agent_uuid} - Updating agent with trigger settings")
    if agent_uuid != agent_update.uuid:
        logger.error(f"PUT /agents/{agent_uuid} - UUID in path does not match UUID in body")
        raise HTTPException(status_code=400, detail="UUID in path does not match UUID in body")

    try:
        # Update Agent
        existing_agent = await agent_client.get_agent(agent_uuid)
        if not existing_agent:
            raise HTTPException(status_code=404, detail="Agent to update not found.")

        agent_data_to_update = agent_update.model_dump(include=set(AgentModel.model_fields.keys()))
        updated_agent = AgentModel.model_validate({**existing_agent.model_dump(), **agent_data_to_update})
        await agent_client.save_agent(updated_agent)

        # Update or Create Trigger
        trigger = await agent_client.get_trigger_for_agent(agent_uuid)
        if trigger:
            trigger.trigger_conditions = agent_update.trigger_conditions
            trigger.filter_rules = agent_update.filter_rules.model_dump()
            await agent_client.update_trigger(trigger)
        else:
            await agent_client.create_trigger(
                agent_uuid=agent_uuid,
                trigger_conditions=agent_update.trigger_conditions,
                filter_rules=agent_update.filter_rules.model_dump()
            )

        logger.info(f"PUT /agents/{agent_uuid} - Agent and trigger updated successfully")
        
        # Refetch data to ensure consistency and return
        return await get_agent(agent_uuid)

    except Exception as e:
        logger.error(f"PUT /agents/{agent_uuid} - Error updating agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating agent.")

@router.delete("/agents/{agent_uuid}", status_code=204)
async def delete_agent(agent_uuid: UUID):
    """
    Deletes an agent and its associated trigger.
    """
    logger.info(f"DELETE /agents/{agent_uuid} - Deleting agent")
    try:
        # First, check if the agent exists to avoid orphaned triggers
        agent = await agent_client.get_agent(agent_uuid)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Delete the trigger if it exists
        trigger = await agent_client.get_trigger_for_agent(agent_uuid)
        if trigger:
            await agent_client.delete_trigger(trigger.uuid)
            logger.info(f"DELETE /agents/{agent_uuid} - Deleted associated trigger {trigger.uuid}")

        # Delete the agent
        await agent_client.delete_agent(agent_uuid)
        logger.info(f"DELETE /agents/{agent_uuid} - Agent deleted successfully")

        return

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"DELETE /agents/{agent_uuid} - Error deleting agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error deleting agent.")

@router.get("/tools")
async def discover_tools():
    """
    Discovers all available tools from all connected MCP servers.
    """
    logger.info("GET /tools - Discovering tools")
    try:
        tools = await agent_client.discover_mcp_tools()
        logger.info(f"GET /tools - Found {len(tools)} tools")
        return tools
    except Exception as e:
        logger.error(f"GET /tools - Error discovering tools: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error discovering tools.")

@router.post("/agents", response_model=AgentWithTriggerSettings, status_code=201)
async def create_agent(request: CreateAgentRequest):
    """
    Creates a new agent and its associated trigger.
    """
    logger.info(f"POST /agents - Creating new agent with name: {request.name}")
    try:
        # 1. Create the Agent
        system_prompt = (
            "You are an agent that should follow the user instructions and execute tasks, using the tools provided to you.\n"
            "The user will provide you with instructions on what to do. Follow these dilligently."
        )
        
        new_agent = await agent_client.create_agent(
            name=request.name,
            description=request.description,
            system_prompt=system_prompt,
            user_instructions=request.user_instructions,
            tools={} # Start with no tools enabled
        )

        # 2. Create the associated Trigger
        await agent_client.create_trigger(
            agent_uuid=new_agent.uuid,
            trigger_conditions=request.trigger_conditions,
            filter_rules=request.filter_rules.model_dump()
        )

        # 3. Fetch and return the combined aent and trigger settings
        created_agent_with_settings = await get_agent(new_agent.uuid)
        
        logger.info(f"POST /agents - Successfully created agent {new_agent.uuid}")
        return created_agent_with_settings

    except Exception as e:
        logger.error(f"POST /agents - Error creating agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error creating agent.")

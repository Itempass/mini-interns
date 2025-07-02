import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse
from functools import lru_cache
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.qdrant.qdrant_client import count_points, get_qdrant_client, recreate_collection
from api.background_tasks.inbox_initializer import initialize_inbox
from shared.config import settings
import json
from uuid import UUID
from typing import List
import asyncio
import os
from pathlib import Path

from agent import client as agent_client
from agent.models import AgentModel, TriggerModel
from api.types.api_models.agent import FilterRules
from api.types.api_models.single_agent import (
    AgentWithTriggerSettings, 
    CreateAgentRequest,
    AgentImportModel,
    TemplateInfo,
    CreateFromTemplateRequest
)

router = APIRouter()
logger = logging.getLogger(__name__)

AGENT_TEMPLATES_DIR = Path("api/agent_templates")

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
    Reads the default trigger conditions from the markdown file.
    """
    try:
        with open("api/defaults/triggerconditions_default.md", "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("Default trigger conditions file not found.")
        return "Default trigger conditions not found."

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

@router.post("/agent/reinitialize-inbox")
async def reinitialize_inbox_endpoint(background_tasks: BackgroundTasks):
    """
    Clears existing vector data and triggers the background task to re-initialize the user's inbox.
    If a vectorization process is already running, it will be gracefully interrupted.
    """
    redis_client = get_redis_client()
    status = redis_client.get(RedisKeys.INBOX_INITIALIZATION_STATUS)

    # If a job is currently running, signal it to stop.
    if status == b'running':
        logger.info("An inbox initialization process is already running. Sending interruption signal.")
        redis_client.set(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED, "true")
        # Give the background worker a moment to see the signal and stop
        await asyncio.sleep(1)

    logger.info("Starting inbox re-initialization. Clearing existing collections.")
    
    # Clear existing vector data
    qdrant_client = get_qdrant_client()
    recreate_collection(qdrant_client, "emails")
    recreate_collection(qdrant_client, "email_threads")
    
    logger.info("Collections cleared. Resetting UID and status, then triggering background task.")

    # Reset the last processed UID to start from scratch
    redis_client.delete(RedisKeys.LAST_EMAIL_UID)
    
    # Set the status to "running" immediately to prevent race conditions
    redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "running")
    
    # The background task will update the status upon completion or failure
    background_tasks.add_task(initialize_inbox)
    
    return {"message": "Inbox re-initialization process started."}

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
        if count_points(collection_name="emails") > 0 or count_points(collection_name="email_threads") > 0:
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
                # Create a temporary trigger in memory to get Pydantic defaults
                from agent.models import TriggerModel
                temp_trigger = TriggerModel(
                    agent_uuid=agent.uuid,
                    trigger_conditions=get_default_trigger_conditions(),
                    filter_rules={}
                )
                trigger_settings = {
                    "trigger_conditions": temp_trigger.trigger_conditions,
                    "trigger_bypass": temp_trigger.trigger_bypass,
                    "filter_rules": FilterRules.model_validate(temp_trigger.filter_rules),
                    "trigger_model": temp_trigger.model
                }
            else:
                trigger_settings = {
                    "trigger_conditions": trigger.trigger_conditions,
                    "trigger_bypass": trigger.trigger_bypass,
                    "filter_rules": FilterRules.model_validate(trigger.filter_rules) if trigger.filter_rules else FilterRules(),
                    "trigger_model": trigger.model
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

@router.post("/agents/import", response_model=AgentWithTriggerSettings, status_code=201)
async def import_agent(file: UploadFile = File(...)):
    """
    Imports an agent from a JSON file.
    """
    logger.info("POST /agents/import - Importing agent from file")
    if file.content_type != "application/json":
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a JSON file.")
    
    try:
        contents = await file.read()
        data = json.loads(contents)
        
        import_data = AgentImportModel.model_validate(data)
        
        new_agent = await agent_client.create_agent(
            name=f"{import_data.name} (imported)",
            description=import_data.description,
            system_prompt=import_data.system_prompt,
            user_instructions=import_data.user_instructions,
            tools=import_data.tools,
            model=getattr(import_data, 'model', None)
        )
        
        new_agent.paused = import_data.paused
        await agent_client.save_agent(new_agent)

        await agent_client.create_trigger(
            agent_uuid=new_agent.uuid,
            trigger_conditions=import_data.trigger_conditions,
            filter_rules=import_data.filter_rules.model_dump(),
            trigger_bypass=import_data.trigger_bypass,
            model=getattr(import_data, 'trigger_model', None)
        )

        imported_agent_with_trigger = await get_agent(new_agent.uuid)
        
        logger.info(f"POST /agents/import - Agent '{new_agent.name}' imported successfully with UUID {new_agent.uuid}")
        return imported_agent_with_trigger

    except json.JSONDecodeError:
        logger.warning("POST /agents/import - Invalid JSON file provided")
        raise HTTPException(status_code=400, detail="Invalid JSON file.")
    except Exception as e:
        logger.error(f"POST /agents/import - Error importing agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error importing agent: {e}")

@router.get("/agents/templates", response_model=List[TemplateInfo])
async def list_agent_templates():
    """
    Lists all available agent templates from the template directory.
    """
    logger.info("GET /agents/templates - Listing all agent templates")
    if not AGENT_TEMPLATES_DIR.is_dir():
        logger.warning(f"Agent templates directory not found at {AGENT_TEMPLATES_DIR}")
        return []
    
    templates = []
    for f in AGENT_TEMPLATES_DIR.glob("*.json"):
        try:
            with open(f, "r") as template_file:
                data = json.load(template_file)
                templates.append(TemplateInfo(
                    id=f.stem,
                    name=data.get("name", "Unnamed Template"),
                    description=data.get("description", "No description available.")
                ))
        except Exception as e:
            logger.error(f"Error reading or parsing template file {f}: {e}")

    logger.info(f"GET /agents/templates - Found {len(templates)} templates.")
    return templates

@router.post("/agents/from-template", response_model=AgentWithTriggerSettings, status_code=201)
async def create_agent_from_template(request: CreateFromTemplateRequest):
    """
    Creates a new agent from a specified template.
    """
    logger.info(f"POST /agents/from-template - Creating agent from template '{request.template_id}'")
    template_file_path = AGENT_TEMPLATES_DIR / f"{request.template_id}.json"

    if not template_file_path.is_file():
        logger.error(f"Template file not found: {template_file_path}")
        raise HTTPException(status_code=404, detail=f"Template '{request.template_id}' not found.")

    try:
        with open(template_file_path, "r") as f:
            data = json.load(f)

        import_data = AgentImportModel.model_validate(data)
        
        new_agent = await agent_client.create_agent(
            name=f"{import_data.name} (from template)",
            description=import_data.description,
            system_prompt=import_data.system_prompt,
            user_instructions=import_data.user_instructions,
            tools=import_data.tools,
            model=getattr(import_data, 'model', None)
        )
        
        new_agent.paused = import_data.paused
        await agent_client.save_agent(new_agent)

        await agent_client.create_trigger(
            agent_uuid=new_agent.uuid,
            trigger_conditions=import_data.trigger_conditions,
            filter_rules=import_data.filter_rules.model_dump(),
            trigger_bypass=import_data.trigger_bypass,
            model=getattr(import_data, 'trigger_model', None)
        )

        created_agent_with_trigger = await get_agent(new_agent.uuid)
        
        logger.info(f"POST /agents/from-template - Agent '{new_agent.name}' created successfully with UUID {new_agent.uuid}")
        return created_agent_with_trigger

    except Exception as e:
        logger.error(f"POST /agents/from-template - Error creating agent from template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating agent from template: {e}")

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
            # Create a temporary trigger in memory to get Pydantic defaults
            from agent.models import TriggerModel
            temp_trigger = TriggerModel(
                agent_uuid=agent_uuid,
                trigger_conditions=get_default_trigger_conditions(),
                filter_rules={}
            )
            trigger_settings = {
                "trigger_conditions": temp_trigger.trigger_conditions,
                "trigger_bypass": temp_trigger.trigger_bypass,
                "filter_rules": FilterRules.model_validate(temp_trigger.filter_rules),
                "trigger_model": temp_trigger.model
            }
        else:
            trigger_settings = {
                "trigger_conditions": trigger.trigger_conditions,
                "trigger_bypass": trigger.trigger_bypass,
                "filter_rules": FilterRules.model_validate(trigger.filter_rules) if trigger.filter_rules else FilterRules(),
                "trigger_model": trigger.model
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
            trigger.trigger_bypass = agent_update.trigger_bypass
            trigger.model = agent_update.trigger_model
            await agent_client.update_trigger(trigger)
        else:
            await agent_client.create_trigger(
                agent_uuid=agent_uuid,
                trigger_conditions=agent_update.trigger_conditions,
                filter_rules=agent_update.filter_rules.model_dump(),
                trigger_bypass=agent_update.trigger_bypass,
                model=agent_update.trigger_model
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
            tools={}, # Start with no tools enabled
            model=request.model
        )

        # 2. Create the associated Trigger
        await agent_client.create_trigger(
            agent_uuid=new_agent.uuid,
            trigger_conditions=request.trigger_conditions,
            filter_rules=request.filter_rules.model_dump(),
            model=request.trigger_model
        )

        # 3. Fetch and return the combined aent and trigger settings
        created_agent_with_settings = await get_agent(new_agent.uuid)
        
        logger.info(f"POST /agents - Successfully created agent {new_agent.uuid}")
        return created_agent_with_settings

    except Exception as e:
        logger.error(f"POST /agents - Error creating agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error creating agent.")

@router.get("/agents/{agent_uuid}/export", response_model=AgentImportModel)
async def export_agent(agent_uuid: UUID):
    """
    Exports a specific agent's settings as a JSON file.
    """
    logger.info(f"GET /agents/{agent_uuid}/export - Exporting agent")
    try:
        agent = await agent_client.get_agent(agent_uuid)
        if not agent:
            logger.warning(f"GET /agents/{agent_uuid}/export - Agent not found")
            raise HTTPException(status_code=404, detail="Agent not found")

        trigger = await agent_client.get_trigger_for_agent(agent_uuid)
        if not trigger:
            # Create a temporary trigger in memory to get Pydantic defaults
            from agent.models import TriggerModel
            temp_trigger = TriggerModel(
                agent_uuid=agent_uuid,
                trigger_conditions=get_default_trigger_conditions(),
                filter_rules={}
            )
            trigger_settings = {
                "trigger_conditions": temp_trigger.trigger_conditions,
                "trigger_bypass": temp_trigger.trigger_bypass,
                "filter_rules": FilterRules.model_validate(temp_trigger.filter_rules),
                "trigger_model": temp_trigger.model
            }
        else:
            trigger_settings = {
                "trigger_conditions": trigger.trigger_conditions,
                "trigger_bypass": trigger.trigger_bypass,
                "filter_rules": FilterRules.model_validate(trigger.filter_rules) if trigger.filter_rules else FilterRules(),
                "trigger_model": trigger.model
            }
        
        export_data = {
            "name": agent.name,
            "description": agent.description,
            "system_prompt": agent.system_prompt,
            "user_instructions": agent.user_instructions,
            "tools": agent.tools,
            "paused": agent.paused,
            "model": agent.model,
            **trigger_settings,
        }
        
        import_model = AgentImportModel.model_validate(export_data)

        headers = {
            'Content-Disposition': f'attachment; filename="{agent.name}.json"'
        }
        return JSONResponse(content=import_model.model_dump(), headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GET /agents/{agent_uuid}/export - Error exporting agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error exporting agent.")

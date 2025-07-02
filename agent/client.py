from __future__ import annotations
from typing import List, Dict, Any
from uuid import UUID
import httpx
from fastmcp import Client

from agent.models import AgentModel, AgentInstanceModel, TriggerModel
from agent.internals.database import (
    _create_agent_in_db,
    _get_agent_from_db,
    _list_agents_from_db,
    _update_agent_in_db,
    _delete_agent_from_db,
    _create_instance_in_db,
    _update_instance_in_db,
    _create_trigger_in_db,
    _get_trigger_from_db,
    _get_trigger_for_agent_from_db,
    _list_triggers_from_db,
    _update_trigger_in_db,
    _delete_trigger_from_db,
)
from agent.internals.runner import _execute_run
from shared.config import settings


# --- Agent Functions ---
async def create_agent(
    name: str,
    description: str,
    system_prompt: str,
    user_instructions: str,
    tools: Dict[str, Any] | None = None,
    model: str | None = None,
) -> AgentModel:
    """
    Creates a new Agent, persists it to the database, and returns the Pydantic model.
    """
    agent_data = {
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "user_instructions": user_instructions,
        "tools": tools or {},
    }
    if model is not None:
        agent_data["model"] = model
    
    agent_model = AgentModel(**agent_data)
    await _create_agent_in_db(agent_model)
    return agent_model

async def get_agent(uuid: UUID) -> AgentModel | None:
    """
    Retrieves an existing Agent from the database.
    """
    return await _get_agent_from_db(uuid)

async def list_agents() -> List[AgentModel]:
    """
    Lists all available agents from the database.
    """
    return await _list_agents_from_db()

async def save_agent(agent_model: AgentModel) -> None:
    """
    Saves the current state of the Agent to the database.
    """
    await _update_agent_in_db(agent_model)

async def delete_agent(uuid: UUID) -> None:
    """
    Deletes an agent from the database.
    """
    await _delete_agent_from_db(uuid)

# --- Tooling Functions ---
async def discover_mcp_tools() -> List[Dict[str, Any]]:
    """
    Discovers all available tools from all connected MCP servers.
    """
    discovered_tools = []
    try:
        api_url = f"http://localhost:{settings.CONTAINERPORT_API}/mcp/servers"
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(api_url)
            response.raise_for_status()
            servers = response.json()
            
            for server in servers:
                server_name = server.get("name")
                mcp_server_url = server.get("url")
                if not server_name or not mcp_server_url:
                    continue

                mcp_client = Client(mcp_server_url)
                async with mcp_client as client:
                    tools_from_server = await client.list_tools()
                    for tool in tools_from_server:
                        discovered_tools.append({
                            "id": f"{server_name}-{tool.name}",
                            "name": tool.name,
                            "description": tool.description,
                            "server": server_name,
                            "input_schema": tool.inputSchema,
                        })

    except Exception:
        # In a real app, you'd want to handle this more gracefully.
        # For now, we'll return an empty list if discovery fails.
        return []
    
    return discovered_tools

# --- AgentInstance Functions ---
async def create_agent_instance(agent_uuid: UUID, user_input: str, context_identifier: str | None = None) -> AgentInstanceModel:
    """
    Creates a new, persistent instance of this agent for a specific run.
    """
    instance_model = AgentInstanceModel(
        agent_uuid=agent_uuid, 
        user_input=user_input, 
        context_identifier=context_identifier
    )
    await _create_instance_in_db(instance_model)
    return instance_model

async def run_agent_instance(agent_model: AgentModel, instance_model: AgentInstanceModel) -> AgentInstanceModel:
    """
    Runs the agentic loop for this instance.
    """
    completed_model = await _execute_run(agent_model, instance_model)
    await _update_instance_in_db(completed_model)
    return completed_model

# --- Trigger Functions ---

async def create_trigger(
    agent_uuid: UUID,
    trigger_conditions: str,
    filter_rules: Dict[str, Any],
    trigger_bypass: bool = False,
    model: str | None = None,
) -> TriggerModel:
    """
    Creates a new Trigger, persists it to the database, and returns the Pydantic model.
    """
    trigger_data = {
        "agent_uuid": agent_uuid,
        "trigger_conditions": trigger_conditions,
        "filter_rules": filter_rules,
        "trigger_bypass": trigger_bypass,
    }
    if model is not None:
        trigger_data["model"] = model
    
    trigger_model = TriggerModel(**trigger_data)
    await _create_trigger_in_db(trigger_model)
    return trigger_model

async def get_trigger(uuid: UUID) -> TriggerModel | None:
    """
    Retrieves an existing Trigger from the database.
    """
    return await _get_trigger_from_db(uuid)

async def get_trigger_for_agent(agent_uuid: UUID) -> TriggerModel | None:
    """
    Retrieves the trigger associated with a specific agent.
    """
    return await _get_trigger_for_agent_from_db(agent_uuid)

async def list_triggers() -> List[TriggerModel]:
    """
    Lists all Triggers from the database.
    """
    return await _list_triggers_from_db()

async def update_trigger(trigger_model: TriggerModel) -> TriggerModel:
    """
    Saves the current state of the Trigger to the database.
    """
    return await _update_trigger_in_db(trigger_model)

async def delete_trigger(uuid: UUID) -> None:
    """
    Deletes a Trigger from the database.
    """
    await _delete_trigger_from_db(uuid)
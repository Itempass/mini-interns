from __future__ import annotations
from typing import List, Dict, Any
from uuid import UUID
import httpx
from fastmcp import Client

from agent.models import AgentModel, AgentInstanceModel
from agent.internals.database import (
    _create_agent_in_db,
    _get_agent_from_db,
    _update_agent_in_db,
    _create_instance_in_db,
    _update_instance_in_db
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
) -> AgentModel:
    """
    Creates a new Agent, persists it to the database, and returns the Pydantic model.
    """
    agent_model = AgentModel(
        name=name,
        description=description,
        system_prompt=system_prompt,
        user_instructions=user_instructions,
        tools=tools or {},
    )
    await _create_agent_in_db(agent_model)
    return agent_model

async def get_agent(uuid: UUID) -> AgentModel | None:
    """
    Retrieves an existing Agent from the database.
    """
    return await _get_agent_from_db(uuid)

async def save_agent(agent_model: AgentModel) -> None:
    """
    Saves the current state of the Agent to the database.
    """
    await _update_agent_in_db(agent_model)

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
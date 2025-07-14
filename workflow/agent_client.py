"""
Client for managing CustomAgent steps and their instances in the workflow engine.

This module provides functions for the CRUD operations on CustomAgent step
definitions and their corresponding instances. It also includes the logic for
discovering available tools from all connected MCP servers, which will be
migrated from the old agent system.
"""
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from fastmcp import Client

from shared.config import settings
from workflow.internals.database import (
    _create_step_in_db,
    _create_step_instance_in_db,
    _delete_step_in_db,
    _get_step_from_db,
    _update_step_in_db,
    _update_step_instance_in_db,
)
from workflow.internals.agent_runner import run_agent_step
from workflow.internals.output_processor import generate_step_summary_from_prompt
from workflow.models import CustomAgent, CustomAgentInstanceModel

logger = logging.getLogger(__name__)


#
# Tool Discovery
#
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
                        discovered_tools.append(
                            {
                                "id": f"{server_name}-{tool.name}",
                                "name": tool.name,
                                "description": tool.description,
                                "server": server_name,
                                "input_schema": tool.inputSchema,
                            }
                        )

    except Exception as e:
        logger.error(f"Failed to discover MCP tools: {e}")
        return []

    return discovered_tools


#
# Definition Management
#
async def create(name: str, model: str, system_prompt: str, user_id: UUID) -> CustomAgent:
    """
    Creates a new, standalone CustomAgent step definition.

    This is primarily called by the workflow_client facade.

    Args:
        name: A unique, user-defined name for this step.
        model: The identifier of the language model to be used.
        system_prompt: The system prompt to guide the agent's behavior.
        user_id: The ID of the user creating the step.

    Returns:
        The created CustomAgent object.
    """
    agent_step = CustomAgent(
        user_id=user_id, name=name, model=model, system_prompt=system_prompt
    )
    await _create_step_in_db(step=agent_step, user_id=user_id)
    return agent_step


async def get(uuid: UUID, user_id: UUID) -> Optional[CustomAgent]:
    """
    Retrieves a CustomAgent step definition by its UUID.

    Args:
        uuid: The UUID of the CustomAgent step to retrieve.
        user_id: The ID of the user owning the step.

    Returns:
        The retrieved CustomAgent object, or None if not found or if the
        retrieved step is not a CustomAgent.
    """
    step = await _get_step_from_db(uuid=uuid, user_id=user_id)
    if isinstance(step, CustomAgent):
        return step
    return None


async def update(agent_model: CustomAgent, user_id: UUID) -> CustomAgent:
    """
    Saves the state of a CustomAgent step definition to the database.
    This also regenerates the summary from the system prompt.

    Args:
        agent_model: The CustomAgent object to save.
        user_id: The ID of the user owning the step.

    Returns:
        The updated CustomAgent object.
    """
    agent_model.generated_summary = generate_step_summary_from_prompt(agent_model.system_prompt)
    await _update_step_in_db(step=agent_model, user_id=user_id)
    return agent_model


async def delete(uuid: UUID, user_id: UUID) -> None:
    """
    Deletes a CustomAgent step definition from the database.

    Args:
        uuid: The UUID of the CustomAgent step to delete.
        user_id: The ID of the user owning the step.
    """
    await _delete_step_in_db(uuid=uuid, user_id=user_id)


#
# Instance Management
#
async def execute_step(
    instance: CustomAgentInstanceModel,
    agent_definition: CustomAgent,
    resolved_system_prompt: str,
) -> CustomAgentInstanceModel:
    """
    Executes a CustomAgent step by invoking the specialized agent runner.

    Args:
        instance: The specific instance of the agent step to run.
        agent_definition: The definition of the agent.
        resolved_system_prompt: The fully resolved system prompt with data from previous steps.

    Returns:
        The updated instance after the execution is complete.
    """
    return await run_agent_step(
        instance=instance,
        agent_definition=agent_definition,
        resolved_system_prompt=resolved_system_prompt,
    )


async def create_instance(
    workflow_instance_uuid: UUID, agent_definition_uuid: UUID, user_id: UUID
) -> CustomAgentInstanceModel:
    """
    Creates a record for a new CustomAgentInstanceModel run.

    This is called by the workflow runner to initialize a step instance.

    Args:
        workflow_instance_uuid: The UUID of the parent workflow instance.
        agent_definition_uuid: The UUID of the CustomAgent definition being executed.
        user_id: The ID of the user running the workflow.

    Returns:
        The created CustomAgentInstanceModel object.
    """
    instance = CustomAgentInstanceModel(
        user_id=user_id,
        workflow_instance_uuid=workflow_instance_uuid,
        agent_definition_uuid=agent_definition_uuid,
        status="pending",
    )
    await _create_step_instance_in_db(instance=instance, user_id=user_id)
    return instance


async def save_instance(
    instance: CustomAgentInstanceModel, user_id: UUID
) -> CustomAgentInstanceModel:
    """
    Updates the state of a CustomAgentInstanceModel during and after execution.

    Args:
        instance: The CustomAgentInstanceModel object to save.
        user_id: The ID of the user owning the instance.

    Returns:
        The updated CustomAgentInstanceModel object.
    """
    await _update_step_instance_in_db(instance=instance, user_id=user_id)
    return instance 
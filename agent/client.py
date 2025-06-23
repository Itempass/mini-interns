from __future__ import annotations
from typing import List, Dict, Any
from uuid import UUID
from agent.models import AgentModel, AgentInstanceModel, TriggerModel
from agent.internals.database import (
    _create_agent_in_db,
    _get_agent_from_db,
    _update_agent_in_db,
    _create_instance_in_db,
    _update_instance_in_db,
    _create_trigger_in_db,
    _get_trigger_from_db,
    _update_trigger_in_db,
)
from agent.internals.runner import _execute_run


# --- Agent Functions ---
async def create_agent(
    name: str,
    description: str,
    system_prompt: str,
    user_instructions: str,
) -> AgentModel:
    """
    Creates a new Agent, persists it to the database, and returns the Pydantic model.
    """
    agent_model = AgentModel(
        name=name,
        description=description,
        system_prompt=system_prompt,
        user_instructions=user_instructions
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

# --- AgentInstance Functions ---
async def create_agent_instance(agent_uuid: UUID, user_input: str) -> AgentInstanceModel:
    """
    Creates a new, persistent instance of this agent for a specific run.
    """
    instance_model = AgentInstanceModel(agent_uuid=agent_uuid, user_input=user_input)
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
    function_name: str,
    rules_json: Dict[str, Any],
) -> TriggerModel:
    """
    Creates a new Trigger, persists it to the database, and returns the Pydantic model.
    """
    trigger_model = TriggerModel(
        agent_uuid=agent_uuid,
        function_name=function_name,
        rules_json=rules_json
    )
    await _create_trigger_in_db(trigger_model)
    return trigger_model

async def get_trigger(uuid: UUID) -> TriggerModel | None:
    """
    Retrieves an existing Trigger from the database.
    """
    return await _get_trigger_from_db(uuid)

async def save_trigger(trigger_model: TriggerModel) -> None:
    """
    Saves the current state of the Trigger to the database.
    """
    await _update_trigger_in_db(trigger_model) 
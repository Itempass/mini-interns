"""
Client for managing Workflows and their instances.

This module serves as the primary entry point for all workflow-related
operations. It provides a high-level orchestration facade for managing the
entire lifecycle of a workflow, from its definition and structure to its
execution and cancellation.

The client orchestrates calls to more specialized clients (for steps and
triggers) and the underlying database layer to present a unified and
consistent API for workflow management.
"""
import logging
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
import asyncio
from workflow.internals import runner

import workflow.agent_client as agent_client
import workflow.checker_client as checker_client
import workflow.internals.database as db
import workflow.llm_client as llm_client
import workflow.trigger_client as trigger_client
from workflow.internals.database import (
    _append_step_to_workflow_in_db,
    _get_step_from_db,
    _get_step_output_data_from_db,
    _get_workflow_from_db,
    _get_workflow_instance_from_db,
    _list_workflow_instances_from_db,
    _list_workflows_from_db,
    _remove_step_from_workflow_in_db,
    _update_workflow_in_db,
)
from workflow.internals.output_processor import create_output_data, generate_summary
from workflow.models import (
    StepOutputData,
    WorkflowInstanceModel,
    WorkflowModel,
    WorkflowWithDetails,
    WorkflowStep,
    InitialWorkflowData,
)
import json

logger = logging.getLogger(__name__)


#
# Definition Management
#

async def create(name: str, description: str, user_id: UUID) -> WorkflowModel:
    """Creates a new, empty workflow."""
    workflow = WorkflowModel(user_id=user_id, name=name, description=description)
    await db._create_workflow_in_db(workflow=workflow, user_id=user_id)
    return workflow


async def get(uuid: UUID, user_id: UUID) -> Optional[WorkflowModel]:
    """Retrieves a workflow definition."""
    return await _get_workflow_from_db(uuid=uuid, user_id=user_id)


async def save(workflow: WorkflowModel, user_id: UUID) -> WorkflowModel:
    """Saves/updates a workflow definition."""
    return await db._update_workflow_in_db(workflow=workflow, user_id=user_id)


async def get_with_details(
    workflow_uuid: UUID, user_id: UUID
) -> Optional[WorkflowWithDetails]:
    """
    Retrieves a single, "hydrated" workflow object with all its step
    and trigger objects fully populated. This is the primary method for
    fetching workflow data for a UI.
    """
    # Get the base workflow model
    workflow = await _get_workflow_from_db(uuid=workflow_uuid, user_id=user_id)
    if not workflow:
        return None

    # Get the associated trigger, if any
    trigger = None
    if workflow.trigger_uuid:
        trigger = await trigger_client.get(uuid=workflow.trigger_uuid, user_id=user_id)

    # Get all the step definitions, maintaining order
    steps = []
    for step_uuid in workflow.steps:
        step = await _get_step_from_db(uuid=step_uuid, user_id=user_id)
        if step:
            steps.append(step)

    # Assemble and return the detailed model
    return WorkflowWithDetails(
        uuid=workflow.uuid,
        user_id=workflow.user_id,
        name=workflow.name,
        description=workflow.description,
        is_active=workflow.is_active,
        trigger=trigger,
        steps=steps,
        template_id=workflow.template_id,
        template_version=workflow.template_version,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


async def list_all(user_id: UUID) -> List[WorkflowModel]:
    """Lists all workflow definitions for a user."""
    return await _list_workflows_from_db(user_id=user_id)


async def delete(uuid: UUID, user_id: UUID) -> None:
    """
    Deletes a workflow definition, its trigger, and all associated steps.
    """
    workflow = await get_with_details(workflow_uuid=uuid, user_id=user_id)
    if not workflow:
        return

    # Delete trigger if it exists
    if workflow.trigger:
        await trigger_client.delete(uuid=workflow.trigger.uuid, user_id=user_id)

    # Delete all steps
    for step in workflow.steps:
        if step.type == "custom_llm":
            await llm_client.delete(uuid=step.uuid, user_id=user_id)
        elif step.type == "custom_agent":
            await agent_client.delete(uuid=step.uuid, user_id=user_id)
        elif step.type == "stop_checker":
            await checker_client.delete(uuid=step.uuid, user_id=user_id)

    # Delete the workflow itself
    await db._delete_workflow_in_db(uuid=uuid, user_id=user_id)

#
# Structure Management
#

async def add_new_step(
    workflow_uuid: UUID,
    step_type: Literal["custom_llm", "custom_agent", "stop_checker"],
    name: str,
    user_id: UUID,
    position: int = -1,
) -> WorkflowModel:
    """
    Creates a new step definition and adds its reference to the workflow.
    This operation is now atomic at the database level.
    """
    # Position is ignored for now as we only support appending.
    # To support insertion at a specific position, a more complex atomic
    # operation (like a stored procedure or a different JSON function) would be needed.
    if position != -1:
        # This would be a more complex operation, for now we raise an error
        # or simply ignore it and append. Let's log a warning.
        logger.warning(f"Positional insertion of steps is not yet supported. Appending to the end.")

    # Create the new step first
    if step_type == "custom_llm":
        new_step = await llm_client.create(name=name, user_id=user_id, model="gpt-4-turbo", system_prompt="")
    elif step_type == "custom_agent":
        new_step = await agent_client.create(name=name, user_id=user_id, model="gpt-4-turbo", system_prompt="")
    elif step_type == "stop_checker":
        new_step = await checker_client.create(name=name, user_id=user_id, stop_conditions=[])
    else:
        raise ValueError(f"Unknown step type: {step_type}")

    # Atomically append the new step's UUID to the workflow's steps list
    await _append_step_to_workflow_in_db(
        workflow_uuid=workflow_uuid, step_uuid=new_step.uuid, user_id=user_id
    )

    # Return the updated workflow
    # Note: get_with_details is called in the API layer, not here.
    return await _get_workflow_from_db(uuid=workflow_uuid, user_id=user_id)


async def update_step(step: WorkflowStep, user_id: UUID) -> Optional[WorkflowStep]:
    """
    Updates a workflow step by calling the appropriate client.
    """
    logger.info(f"Updating step {step.uuid} of type {step.type}")
    if step.type == "custom_llm":
        return await llm_client.update(step, user_id=user_id)
    elif step.type == "custom_agent":
        return await agent_client.update(step, user_id=user_id)
    elif step.type == "stop_checker":
        return await checker_client.update(step, user_id=user_id)
    else:
        logger.error(f"Attempted to update a step with an unknown type: {step.type}")
        return None


async def delete_step(workflow_uuid: UUID, step_uuid: UUID, user_id: UUID) -> None:
    """
    Removes a step from a workflow's list and deletes the step definition.
    This operation is now atomic at the database level.
    """
    # First, get the step definition so we know its type for deletion later.
    step_to_delete = await _get_step_from_db(uuid=step_uuid, user_id=user_id)
    if not step_to_delete:
        logger.warning(f"Attempted to delete step {step_uuid}, but it was not found.")
        return

    # Atomically remove the step's reference from the workflow's `steps` array.
    await _remove_step_from_workflow_in_db(
        workflow_uuid=workflow_uuid, step_uuid=step_uuid, user_id=user_id
    )

    # After successfully removing the reference, delete the step definition itself.
    if step_to_delete.type == "custom_llm":
        await llm_client.delete(uuid=step_uuid, user_id=user_id)
    elif step_to_delete.type == "custom_agent":
        await agent_client.delete(uuid=step_uuid, user_id=user_id)
    elif step_to_delete.type == "stop_checker":
        await checker_client.delete(uuid=step_uuid, user_id=user_id)


async def reorder_steps(
    workflow_uuid: UUID, ordered_step_uuids: List[UUID], user_id: UUID
) -> WorkflowModel:
    """Reorders the `steps` list of a workflow."""
    workflow = await _get_workflow_from_db(uuid=workflow_uuid, user_id=user_id)
    if not workflow:
        raise ValueError("Workflow not found.")
    
    workflow.steps = ordered_step_uuids
    await _update_workflow_in_db(workflow=workflow, user_id=user_id)
    return workflow


async def set_trigger(
    workflow_uuid: UUID, trigger_type_id: str, user_id: UUID
) -> WorkflowModel:
    """
    Creates and attaches a new trigger to the workflow.
    """
    workflow = await _get_workflow_from_db(uuid=workflow_uuid, user_id=user_id)
    if not workflow:
        raise ValueError("Workflow not found.")

    if workflow.trigger_uuid:
        await trigger_client.delete(uuid=workflow.trigger_uuid, user_id=user_id)

    new_trigger = await trigger_client.create(
        workflow_uuid=workflow_uuid,
        trigger_type_id=trigger_type_id,
        user_id=user_id,
    )
    workflow.trigger_uuid = new_trigger.uuid
    await _update_workflow_in_db(workflow=workflow, user_id=user_id)
    return workflow


async def remove_trigger(workflow_uuid: UUID, user_id: UUID) -> WorkflowModel:
    """Detaches and deletes the trigger associated with the workflow."""
    workflow = await _get_workflow_from_db(uuid=workflow_uuid, user_id=user_id)
    if not workflow or not workflow.trigger_uuid:
        return workflow

    await trigger_client.delete(uuid=workflow.trigger_uuid, user_id=user_id)
    workflow.trigger_uuid = None
    await _update_workflow_in_db(workflow=workflow, user_id=user_id)
    return workflow

#
# Execution Management
#

async def create_instance(
    workflow_uuid: UUID, triggering_data: InitialWorkflowData, user_id: UUID
) -> WorkflowInstanceModel:
    """Creates a new instance of a workflow, ready to be run."""
    # The initial trigger data is stored as the first "step output"
    trigger_output = await create_output_data(
        raw_data=triggering_data.raw_data,
        summary=await generate_summary(triggering_data.raw_data),
        user_id=user_id,
    )

    instance = WorkflowInstanceModel(
        user_id=user_id,
        workflow_definition_uuid=workflow_uuid,
        status="running",  # Start in running state
        trigger_output=trigger_output,
    )
    await db._create_workflow_instance_in_db(instance=instance, user_id=user_id)
    logger.info(f"Successfully created workflow instance {instance.uuid} in the database.")

    return instance


async def get_instance(
    instance_uuid: UUID, user_id: UUID
) -> Optional[WorkflowInstanceModel]:
    """
    Retrieves the status and results of a workflow run, including all
    of its executed step instances.
    """
    instance = await _get_workflow_instance_from_db(uuid=instance_uuid, user_id=user_id)
    if not instance:
        return None
    
    # Hydrate the instance with its executed steps
    step_instances = await db._list_step_instances_for_workflow_instance_from_db(
        workflow_instance_uuid=instance_uuid, user_id=user_id
    )
    instance.step_instances = step_instances
    
    return instance


async def get_output_data(output_id: str, user_id: UUID) -> Optional[StepOutputData]:
    """Retrieves a single StepOutputData object from the database by its UUID."""
    # This is a direct passthrough to the internal database function.
    return await db._get_step_output_data_from_db(output_id=UUID(output_id), user_id=user_id)


async def list_instances(
    workflow_uuid: UUID, user_id: UUID
) -> List[WorkflowInstanceModel]:
    """Lists all runs for a given workflow."""
    return await _list_workflow_instances_from_db(
        workflow_uuid=workflow_uuid, user_id=user_id
    )


async def cancel_instance(instance_uuid: UUID, user_id: UUID) -> None:
    """Cancels a running workflow."""
    instance = await get_instance(instance_uuid=instance_uuid, user_id=user_id)
    if instance and instance.status == "running":
        instance.status = "cancelled"
        await db._update_workflow_instance_in_db(instance=instance, user_id=user_id)
        # TODO: Implement logic to gracefully stop the background task


#
# Utility Functions
#

async def list_available_step_types() -> List[Dict[str, Any]]:
    """Returns a list of all available step types that can be added."""
    return [
        {
            "type": "custom_llm",
            "name": "LLM Call",
            "description": "A simple call to a language model with a system prompt.",
        },
        {
            "type": "custom_agent",
            "name": "Agent",
            "description": "An autonomous agent with access to a set of tools.",
        },
        {
            "type": "stop_checker",
            "name": "Stop Workflow",
            "description": "Stops the workflow if certain conditions are met.",
        },
    ]


async def list_available_trigger_types() -> List[Dict[str, Any]]:
    """Returns a list of all available trigger types."""
    return await trigger_client.get_available_types()


async def discover_mcp_tools() -> List[Dict[str, Any]]:
    """Discovers all available tools from all connected MCP servers."""
    return await agent_client.discover_mcp_tools() 
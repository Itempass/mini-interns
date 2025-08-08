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


async def set_active_status(
    workflow_uuid: UUID, is_active: bool, user_id: UUID
) -> Optional[WorkflowModel]:
    """Sets the is_active status of a workflow."""
    workflow = await get(uuid=workflow_uuid, user_id=user_id)
    if not workflow:
        return None

    workflow.is_active = is_active
    return await save(workflow=workflow, user_id=user_id)


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


async def get_step(step_uuid: UUID, user_id: UUID) -> Optional[WorkflowStep]:
    """Retrieves a single workflow step definition by its UUID."""
    return await _get_step_from_db(uuid=step_uuid, user_id=user_id)


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
        elif step.type == "rag":
            # RAG definitions are stored in the generic table too; simply delete the row
            await db._delete_step_in_db(uuid=step.uuid, user_id=user_id)

    # Delete the workflow itself
    await db._delete_workflow_in_db(uuid=uuid, user_id=user_id)

async def update_workflow_details(
    workflow_uuid: UUID,
    name: Optional[str],
    description: Optional[str],
    user_id: UUID,
) -> Optional[WorkflowModel]:
    """Updates the name and/or description of a workflow."""
    workflow = await get(uuid=workflow_uuid, user_id=user_id)
    if not workflow:
        return None

    if name is not None:
        workflow.name = name
    if description is not None:
        workflow.description = description

    # Only update if something changed to avoid unnecessary writes
    if name is not None or description is not None:
        return await save(workflow=workflow, user_id=user_id)
    
    return workflow

async def import_workflow(workflow_data: Dict[str, Any], user_id: UUID) -> WorkflowModel:
    """
    Creates a new workflow from an imported data structure. This involves a
    two-pass process to correctly remap internal step UUID references.
    """
    # 1. Create the new workflow shell
    new_workflow = await create(
        name=f"{workflow_data.get('name', 'Untitled')} (Imported)",
        description=workflow_data.get('description', ''),
        user_id=user_id
    )

    # Pass 1: Create steps and build a UUID mapping
    uuid_map = {}  # { old_uuid: new_uuid }
    new_steps = [] # To hold the newly created step objects
    for step_data in workflow_data.get('steps', []):
        step_type = step_data['type']
        new_step = None

        # Create the step based on its type
        if step_type == "custom_llm":
            new_step = await llm_client.create(
                name=step_data['name'],
                user_id=user_id,
                model=step_data.get('model'),
                system_prompt=step_data.get('system_prompt', '')
            )
        elif step_type == "custom_agent":
            new_step = await agent_client.create(
                name=step_data['name'],
                user_id=user_id,
                model=step_data.get('model'),
                system_prompt=step_data.get('system_prompt', ''),
                tools=step_data.get('tools', {})
            )
        elif step_type == "stop_checker":
            new_step = await checker_client.create(
                name=step_data['name'],
                user_id=user_id,
                check_mode=step_data.get('check_mode', 'stop_if_output_contains'),
                match_values=step_data.get('match_values', []),
                step_to_check_uuid=step_data.get('step_to_check_uuid')
            )
        elif step_type == "rag":
            # Import a RAG step as a generic row; details will be preserved via model structure
            from workflow.models import RAGStep
            new_step = RAGStep(
                user_id=user_id,
                name=step_data['name'],
                system_prompt=step_data.get('system_prompt', ''),
                vectordb_uuid=UUID(step_data['vectordb_uuid']) if isinstance(step_data.get('vectordb_uuid'), str) else step_data.get('vectordb_uuid'),
                rerank=step_data.get('rerank', False),
                top_k=step_data.get('top_k', 5),
            )
            await db._create_step_in_db(step=new_step, user_id=user_id)

        if new_step:
            uuid_map[step_data['uuid']] = new_step.uuid
            new_steps.append(new_step)

    # Pass 2: Update references in the newly created steps
    for step in new_steps:
        # Remap references in system prompts
        if hasattr(step, 'system_prompt') and step.system_prompt:
            for old_uuid, new_uuid in uuid_map.items():
                step.system_prompt = step.system_prompt.replace(str(old_uuid), str(new_uuid))
        
        # Remap references in stop_checker steps
        if step.type == "stop_checker" and hasattr(step, 'step_to_check_uuid') and step.step_to_check_uuid:
            old_ref_uuid = str(step.step_to_check_uuid)
            if old_ref_uuid in uuid_map:
                step.step_to_check_uuid = uuid_map[old_ref_uuid]
        
        # Save the updated step
        await update_step(step, user_id)

    # Assign the new step UUIDs to the workflow
    new_workflow.steps = [step.uuid for step in new_steps]

    # Create and configure the trigger
    if workflow_data.get('trigger'):
        trigger_data = workflow_data['trigger']
        trigger_type_id = "new_email" # Simplified as per previous discussion
        new_trigger = await trigger_client.create(
            workflow_uuid=new_workflow.uuid,
            trigger_type_id=trigger_type_id,
            user_id=user_id
        )
        if trigger_data.get('filter_rules'):
            new_trigger.filter_rules = trigger_data['filter_rules']
            await trigger_client.update(trigger_model=new_trigger, user_id=user_id)
        new_workflow.trigger_uuid = new_trigger.uuid

    # Final Save: Save the workflow with the updated step list and trigger
    await save(workflow=new_workflow, user_id=user_id)
    return new_workflow


#
# Structure Management
#

async def add_new_step(
    workflow_uuid: UUID,
    step_type: Literal["custom_llm", "custom_agent", "stop_checker", "rag"],
    name: str,
    user_id: UUID,
    position: int = -1,
    model: Optional[str] = None,
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

    default_model = "google/gemini-2.5-flash"

    # Create the new step first
    if step_type == "custom_llm":
        new_step = await llm_client.create(name=name, user_id=user_id, model=model or default_model, system_prompt="")
    elif step_type == "custom_agent":
        new_step = await agent_client.create(name=name, user_id=user_id, model=model or default_model, system_prompt="")
    elif step_type == "stop_checker":
        new_step = await checker_client.create(name=name, user_id=user_id)
    elif step_type == "rag":
        from workflow.models import RAGStep
        new_step = RAGStep(user_id=user_id, name=name)
        await db._create_step_in_db(step=new_step, user_id=user_id)
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
    elif step.type == "rag":
        # Generic update for RAG step in the workflow_steps table
        await db._update_step_in_db(step=step, user_id=user_id)
        return step
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
    elif step_to_delete.type == "rag":
        await db._delete_step_in_db(uuid=step_uuid, user_id=user_id)


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
    workflow_uuid: UUID, initial_markdown: str, user_id: UUID
) -> WorkflowInstanceModel:
    """
    Creates a new instance of a workflow, ready to be run.
    """
    # Create the initial output data container that represents the trigger's output.
    trigger_output_data = await create_output_data(
        markdown_representation=initial_markdown,
        user_id=user_id,
    )

    instance = WorkflowInstanceModel(
        user_id=user_id,
        workflow_definition_uuid=workflow_uuid,
        status="running",
        trigger_output=trigger_output_data
    )
    await db._create_workflow_instance_in_db(instance=instance, user_id=user_id)
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
    """Retrieves a single StepOutputData object by its ID."""
    return await _get_step_output_data_from_db(output_id, user_id)


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
        {
            "type": "rag",
            "name": "RAG",
            "description": "Retrieve and optionally rerank results from a vector database, then return a grounded output.",
        },
    ]


async def list_available_trigger_types() -> List[Dict[str, Any]]:
    """Returns a list of all available trigger types."""
    return await trigger_client.get_available_types()


async def discover_mcp_tools() -> List[Dict[str, Any]]:
    """Discovers all available tools from all connected MCP servers."""
    return await agent_client.discover_mcp_tools() 
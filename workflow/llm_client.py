"""
Client for managing CustomLLM steps and their instances in the workflow engine.

This module provides a set of functions to handle the creation, retrieval, updating,
and deletion of CustomLLM step definitions, as well as managing their execution
instances within a workflow run. It acts as a standalone manager for the LLM
domain, interacting with the database layer to persist changes.
"""

from typing import Optional, Any
from uuid import UUID
import logging

from workflow.internals.database import (
    _create_step_in_db,
    _create_step_instance_in_db,
    _delete_step_in_db,
    _get_step_from_db,
    _update_step_in_db,
    _update_step_instance_in_db,
)
from workflow.internals.llm_runner import run_llm_step
from workflow.models import CustomLLM, CustomLLMInstanceModel

logger = logging.getLogger(__name__)

#
# Definition Management
#
async def create(name: str, model: str, system_prompt: str, user_id: UUID) -> CustomLLM:
    """
    Creates a new, standalone CustomLLM step definition.

    This is primarily called by the workflow_client facade when adding a new
    LLM step to a workflow.

    Args:
        name: A unique, user-defined name for this step.
        model: The identifier of the language model to be used.
        system_prompt: The system prompt to guide the LLM's behavior.
        user_id: The ID of the user creating the step.

    Returns:
        The created CustomLLM object.
    """
    llm_step = CustomLLM(
        user_id=user_id, name=name, model=model, system_prompt=system_prompt
    )
    await _create_step_in_db(step=llm_step, user_id=user_id)
    return llm_step


async def get(uuid: UUID, user_id: UUID) -> Optional[CustomLLM]:
    """
    Retrieves a CustomLLM step definition by its UUID.

    Args:
        uuid: The UUID of the CustomLLM step to retrieve.
        user_id: The ID of the user owning the step.

    Returns:
        The retrieved CustomLLM object, or None if not found or if the
        retrieved step is not a CustomLLM.
    """
    step = await _get_step_from_db(uuid=uuid, user_id=user_id)
    if isinstance(step, CustomLLM):
        return step
    return None


async def save(llm_model: CustomLLM, user_id: UUID) -> CustomLLM:
    """
    Saves the state of a CustomLLM step definition to the database.

    Args:
        llm_model: The CustomLLM object to save.
        user_id: The ID of the user owning the step.

    Returns:
        The updated CustomLLM object.
    """
    await _update_step_in_db(step=llm_model, user_id=user_id)
    return llm_model


async def delete(uuid: UUID, user_id: UUID) -> None:
    """
    Deletes a CustomLLM step definition from the database.

    Args:
        uuid: The UUID of the CustomLLM step to delete.
        user_id: The ID of the user owning the step.
    """
    await _delete_step_in_db(uuid=uuid, user_id=user_id)


#
# Instance Management
#


async def execute_step(
    instance: CustomLLMInstanceModel,
    llm_definition: CustomLLM,
    resolved_system_prompt: str,
) -> Any:
    """
    Executes a CustomLLM step by invoking the specialized LLM runner.

    Args:
        instance: The specific instance of the LLM step to run.
        llm_definition: The definition of the LLM step.
        resolved_system_prompt: The fully resolved system prompt.

    Returns:
        The raw output from the language model.
    """
    return await run_llm_step(
        instance=instance,
        llm_definition=llm_definition,
        resolved_system_prompt=resolved_system_prompt,
    )


async def create_instance(
    workflow_instance_uuid: UUID, llm_definition_uuid: UUID, user_id: UUID
) -> CustomLLMInstanceModel:
    """
    Creates a record for a new CustomLLMInstanceModel run.

    This is called by the workflow runner to initialize a step instance,
    typically with a 'pending' status, before execution begins.

    Args:
        workflow_instance_uuid: The UUID of the parent workflow instance.
        llm_definition_uuid: The UUID of the CustomLLM definition being executed.
        user_id: The ID of the user running the workflow.

    Returns:
        The created CustomLLMInstanceModel object.
    """
    instance = CustomLLMInstanceModel(
        user_id=user_id,
        workflow_instance_uuid=workflow_instance_uuid,
        llm_definition_uuid=llm_definition_uuid,
        status="pending",
    )
    await _create_step_instance_in_db(instance=instance, user_id=user_id)
    return instance


async def save_instance(
    instance: CustomLLMInstanceModel, user_id: UUID
) -> CustomLLMInstanceModel:
    """
    Updates the state of a CustomLLMInstanceModel during and after execution.

    Args:
        instance: The CustomLLMInstanceModel object to save.
        user_id: The ID of the user owning the instance.

    Returns:
        The updated CustomLLMInstanceModel object.
    """
    await _update_step_instance_in_db(instance=instance, user_id=user_id)
    return instance 
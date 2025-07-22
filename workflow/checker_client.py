"""
Client for managing StopWorkflowChecker steps and their instances.

This module provides functions for the lifecycle management of StopWorkflowChecker
steps, which are used to conditionally halt a workflow's execution based on
the outputs of previous steps. It handles the CRUD operations for both the
definitions and the execution instances of these checker steps.
"""

from typing import List, Optional
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
from workflow.internals.checker_runner import run_checker_step
from workflow.models import (
    StepOutputData,
    StopWorkflowChecker,
    StopWorkflowCheckerInstanceModel,
)

logger = logging.getLogger(__name__)


#
# Definition Management
#
async def create(
    name: str,
    user_id: UUID,
    check_mode: str = "stop_if_output_contains",
    match_values: Optional[List[str]] = None,
    step_to_check_uuid: Optional[UUID] = None,
) -> StopWorkflowChecker:
    """
    Creates a new, standalone StopWorkflowChecker step definition.

    Args:
        name: A user-defined name for the checker step.
        user_id: The ID of the user creating the step.
        check_mode: The condition to check for.
        match_values: A list of strings to look for in the output.
        step_to_check_uuid: The UUID of the step whose output should be inspected.

    Returns:
        The created StopWorkflowChecker object.
    """
    checker_step = StopWorkflowChecker(
        user_id=user_id,
        name=name,
        check_mode=check_mode,
        match_values=match_values or [],
        step_to_check_uuid=step_to_check_uuid,
    )
    await _create_step_in_db(step=checker_step, user_id=user_id)
    return checker_step


async def get(uuid: UUID, user_id: UUID) -> Optional[StopWorkflowChecker]:
    """
    Retrieves a StopWorkflowChecker step definition by its UUID.

    Args:
        uuid: The UUID of the checker step to retrieve.
        user_id: The ID of the user owning the step.

    Returns:
        The retrieved StopWorkflowChecker object, or None if not found or
        if the step is of a different type.
    """
    step = await _get_step_from_db(uuid=uuid, user_id=user_id)
    if isinstance(step, StopWorkflowChecker):
        return step
    return None


async def update(
    checker_model: StopWorkflowChecker, user_id: UUID
) -> StopWorkflowChecker:
    """
    Saves the state of a StopWorkflowChecker step definition.

    Args:
        checker_model: The StopWorkflowChecker object to save.
        user_id: The ID of the user owning the step.

    Returns:
        The updated StopWorkflowChecker object.
    """
    logger.debug(f"Received checker_model for update: {checker_model}")

    # The database layer's JSON serializer cannot handle UUID objects.
    # We need to temporarily convert the UUID to a string for the DB call.
    original_uuid = checker_model.step_to_check_uuid
    try:
        if isinstance(original_uuid, UUID):
            # Use object.__setattr__ to bypass Pydantic's validation, which would
            # otherwise convert our string back into a UUID object.
            logger.debug(f"Temporarily converting step_to_check_uuid ({original_uuid}) to string for DB serialization.")
            object.__setattr__(checker_model, 'step_to_check_uuid', str(original_uuid))

        await _update_step_in_db(step=checker_model, user_id=user_id)
    finally:
        # Always restore the original UUID object to the model to ensure
        # consistency for any subsequent operations in the call stack.
        logger.debug(f"Restoring original UUID to checker_model.")
        object.__setattr__(checker_model, 'step_to_check_uuid', original_uuid)
    
    return checker_model


async def delete(uuid: UUID, user_id: UUID) -> None:
    """
    Deletes a StopWorkflowChecker step definition.

    Args:
        uuid: The UUID of the checker step to delete.
        user_id: The ID of the user owning the step.
    """
    await _delete_step_in_db(uuid=uuid, user_id=user_id)


#
# Instance Management
#
async def execute_step(
    instance: StopWorkflowCheckerInstanceModel,
    step_definition: StopWorkflowChecker,
    step_outputs: dict[UUID, StepOutputData],
) -> bool:
    """
    Executes a StopWorkflowChecker step by invoking the specialized runner.

    Args:
        instance: The specific instance of the checker step to run.
        step_definition: The definition of the checker step.
        step_outputs: A dictionary of all previous step outputs.

    Returns:
        True if the workflow should stop, False otherwise.
    """
    return await run_checker_step(
        instance=instance,
        step_definition=step_definition,
        step_outputs=step_outputs,
    )


async def create_instance(
    workflow_instance_uuid: UUID, checker_definition_uuid: UUID, user_id: UUID
) -> StopWorkflowCheckerInstanceModel:
    """
    Creates a record for a new StopWorkflowCheckerInstanceModel run.

    Args:
        workflow_instance_uuid: The UUID of the parent workflow instance.
        checker_definition_uuid: The UUID of the checker definition being run.
        user_id: The ID of the user running the workflow.

    Returns:
        The created StopWorkflowCheckerInstanceModel object.
    """
    instance = StopWorkflowCheckerInstanceModel(
        user_id=user_id,
        workflow_instance_uuid=workflow_instance_uuid,
        checker_definition_uuid=checker_definition_uuid,
        status="pending",
    )
    await _create_step_instance_in_db(instance=instance, user_id=user_id)
    return instance


async def save_instance(
    instance: StopWorkflowCheckerInstanceModel, user_id: UUID
) -> StopWorkflowCheckerInstanceModel:
    """
    Updates the state of a StopWorkflowCheckerInstanceModel.

    Args:
        instance: The StopWorkflowCheckerInstanceModel object to save.
        user_id: The ID of the user owning the instance.

    Returns:
        The updated StopWorkflowCheckerInstanceModel object.
    """
    await _update_step_instance_in_db(instance=instance, user_id=user_id)
    return instance 
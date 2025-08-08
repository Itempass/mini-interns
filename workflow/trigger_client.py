"""
Client for managing TriggerModel definitions in the workflow engine.

This module provides a standalone manager for handling the lifecycle of
triggers, which are responsible for initiating workflow instances. It includes
functions for creating, retrieving, updating, and deleting trigger definitions,
as well as listing the available types of triggers that can be used.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from workflow.internals.database import (
    _create_trigger_in_db,
    _delete_trigger_in_db,
    _get_trigger_for_workflow_from_db,
    _get_trigger_from_db,
    _list_triggers_from_db,
    _update_trigger_in_db,
)
from workflow.models import TriggerModel

# A hardcoded list of available trigger types for now.
# In the future, this could be loaded from a configuration file or database.
AVAILABLE_TRIGGER_TYPES = [
    {
        "id": "new_email",
        "name": "When I receive a new email",
        "description": "Checks your inbox every minute for new emails, triggers a workflow when a new email is received and the filters are met.",
        "initial_data_description": "The full content and metadata of the new email.",
    }
]


async def get_available_types() -> List[Dict[str, Any]]:
    """
    Returns a list of available trigger types for the UI to display.

    Returns:
        A list of dictionaries, each describing an available trigger type.
    """
    return AVAILABLE_TRIGGER_TYPES


async def create(
    workflow_uuid: UUID, trigger_type_id: str, user_id: UUID
) -> TriggerModel:
    """
    Creates a new trigger with default settings for the given type.

    This is primarily called by the workflow_client facade.

    Args:
        workflow_uuid: The UUID of the workflow this trigger belongs to.
        trigger_type_id: The identifier of the trigger type to create.
        user_id: The ID of the user creating the trigger.

    Returns:
        The created TriggerModel object.

    Raises:
        ValueError: If the trigger_type_id is not found.
    """
    trigger_type = next(
        (t for t in AVAILABLE_TRIGGER_TYPES if t["id"] == trigger_type_id), None
    )
    if not trigger_type:
        raise ValueError(f"Trigger type '{trigger_type_id}' not found.")

    trigger = TriggerModel(
        user_id=user_id,
        workflow_uuid=workflow_uuid,
        initial_data_description=trigger_type["initial_data_description"],
    )
    await _create_trigger_in_db(trigger=trigger, user_id=user_id)
    return trigger


async def get(uuid: UUID, user_id: UUID) -> Optional[TriggerModel]:
    """
    Retrieves a trigger by its UUID.

    Args:
        uuid: The UUID of the trigger to retrieve.
        user_id: The ID of the user owning the trigger.

    Returns:
        The trigger, or None if not found.
    """
    return await _get_trigger_from_db(uuid=uuid, user_id=user_id)


async def get_for_workflow(
    workflow_uuid: UUID, user_id: UUID
) -> Optional[TriggerModel]:
    """
    Retrieves the trigger for a specific workflow.

    Args:
        workflow_uuid: The UUID of the workflow whose trigger is to be retrieved.
        user_id: The ID of the user owning the workflow.

    Returns:
        The trigger associated with the workflow, or None if not found.
    """
    return await _get_trigger_for_workflow_from_db(
        workflow_uuid=workflow_uuid, user_id=user_id
    )


async def list_triggers(user_id: UUID) -> List[TriggerModel]:
    """
    Lists all triggers for a given user.

    Args:
        user_id: The ID of the user whose triggers are to be listed.

    Returns:
        A list of TriggerModel objects.
    """
    return await _list_triggers_from_db(user_id=user_id)


async def update(trigger_model: TriggerModel, user_id: UUID) -> TriggerModel:
    """
    Updates the state of a trigger definition in the database.

    Args:
        trigger_model: The TriggerModel object to update.
        user_id: The ID of the user owning the trigger.

    Returns:
        The updated TriggerModel object.
    """
    await _update_trigger_in_db(trigger=trigger_model, user_id=user_id)
    return trigger_model


async def save(trigger_model: TriggerModel, user_id: UUID) -> TriggerModel:
    """
    Updates the state of a trigger definition in the database.

    Args:
        trigger_model: The TriggerModel object to save.
        user_id: The ID of the user owning the trigger.

    Returns:
        The updated TriggerModel object.
    """
    await _update_trigger_in_db(trigger=trigger_model, user_id=user_id)
    return trigger_model


async def delete(uuid: UUID, user_id: UUID) -> None:
    """
    Deletes a trigger definition from the database.

    Args:
        uuid: The UUID of the trigger to delete.
        user_id: The ID of the user owning the trigger.
    """
    await _delete_trigger_in_db(uuid=uuid, user_id=user_id) 
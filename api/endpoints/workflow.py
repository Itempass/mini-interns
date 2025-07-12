import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

import workflow.client as workflow_client
import workflow.internals.runner as runner
from workflow.models import (
    StepOutputData,
    WorkflowInstanceModel,
    WorkflowModel,
    WorkflowWithDetails,
)

from ..types.api_models.workflow import (
    CreateWorkflowRequest,
    SetTriggerRequest,
    TriggerTypeResponse,
)
from .auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["Workflows"])


#
# Workflow Definition Endpoints
#
@router.post(
    "",
    response_model=WorkflowModel,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workflow",
)
async def create_workflow(
    request: CreateWorkflowRequest, user_id: UUID = Depends(get_current_user_id)
):
    """Creates a new, empty workflow definition."""
    return await workflow_client.create(
        name=request.name, description=request.description, user_id=user_id
    )


@router.get(
    "", response_model=List[WorkflowModel], summary="List all workflows"
)
async def list_workflows(user_id: UUID = Depends(get_current_user_id)):
    """Lists all workflow definitions for the current user."""
    return await workflow_client.list_all(user_id=user_id)


#
# Utility & Data Endpoints
#
@router.get(
    "/outputs/{output_id}",
    response_model=StepOutputData,
    summary="Get output data from a step",
)
async def get_step_output(
    output_id: UUID, user_id: UUID = Depends(get_current_user_id)
):
    """
    Retrieves the full StepOutputData object for a given output ID.
    This can be used by agents with the `get_step_output` tool.
    """
    output_data = await workflow_client.get_output_data(
        output_id=output_id, user_id=user_id
    )
    if not output_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Output data not found"
        )
    return output_data


@router.get(
    "/available-step-types",
    response_model=List[dict],
    summary="List available step types",
)
async def get_available_step_types():
    """Returns a list of available step types that can be added to a workflow."""
    return await workflow_client.list_available_step_types()


@router.get(
    "/available-trigger-types",
    response_model=List[TriggerTypeResponse],
    summary="List available trigger types",
)
async def get_available_trigger_types() -> List[TriggerTypeResponse]:
    """Returns a list of available trigger types that can be added to a workflow."""
    logger.info("Fetching available trigger types from workflow_client")
    try:
        trigger_types = await workflow_client.list_available_trigger_types()
        logger.info(f"Successfully fetched trigger types: {trigger_types}")
        return trigger_types
    except Exception as e:
        logger.error(f"Error fetching trigger types: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Error fetching available trigger types."
        )


@router.get(
    "/{workflow_uuid}",
    response_model=WorkflowWithDetails,
    summary="Get a single workflow with details",
)
async def get_workflow_details(
    workflow_uuid: UUID, user_id: UUID = Depends(get_current_user_id)
):
    """
    Retrieves a single, "hydrated" workflow object with all its step
    and trigger objects fully populated.
    """
    workflow = await workflow_client.get_with_details(
        workflow_uuid=workflow_uuid, user_id=user_id
    )
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found"
        )
    return workflow


@router.delete(
    "/{workflow_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workflow",
)
async def delete_workflow(
    workflow_uuid: UUID, user_id: UUID = Depends(get_current_user_id)
):
    """
    Deletes a workflow definition, its trigger, and all associated steps.
    """
    logger.info(f"DELETE /workflows/{workflow_uuid} - Deleting workflow")
    try:
        # Check if the workflow exists
        workflow = await workflow_client.get(uuid=workflow_uuid, user_id=user_id)
        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found"
            )

        # Delete the workflow and all its associated components
        await workflow_client.delete(uuid=workflow_uuid, user_id=user_id)
        logger.info(f"DELETE /workflows/{workflow_uuid} - Workflow deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"DELETE /workflows/{workflow_uuid} - Error deleting workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error deleting workflow.")


#
# Workflow Execution Endpoints
#
@router.post(
    "/{workflow_uuid}/run",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run a workflow",
)
async def run_workflow_endpoint(
    workflow_uuid: UUID,
    triggering_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Creates a new workflow instance and starts its execution in the background.
    """
    instance = await workflow_client.create_instance(
        workflow_uuid=workflow_uuid, triggering_data=triggering_data, user_id=user_id
    )
    # This adds the long-running task to FastAPI's background runner
    background_tasks.add_task(runner.run_workflow, instance.uuid, user_id)

    return {"message": "Workflow run started.", "instance_id": instance.uuid}


@router.get(
    "/instances/{instance_uuid}",
    response_model=WorkflowInstanceModel,
    summary="Get a workflow instance",
)
async def get_workflow_instance(
    instance_uuid: UUID, user_id: UUID = Depends(get_current_user_id)
):
    """Retrieves the status and results of a specific workflow run."""
    instance = await workflow_client.get_instance(
        instance_uuid=instance_uuid, user_id=user_id
    )
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow instance not found"
        )
    return instance


#
# Utility & Data Endpoints
#
@router.get(
    "/outputs/{output_id}",
    response_model=StepOutputData,
    summary="Get output data from a step",
)
async def get_step_output(
    output_id: UUID, user_id: UUID = Depends(get_current_user_id)
):
    """
    Retrieves the full StepOutputData object for a given output ID.
    This can be used by agents with the `get_step_output` tool.
    """
    output_data = await workflow_client.get_output_data(
        output_id=output_id, user_id=user_id
    )
    if not output_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Output data not found"
        )
    return output_data


@router.get(
    "/available-step-types",
    response_model=List[dict],
    summary="List available step types",
)
async def get_available_step_types():
    """Returns a list of available step types that can be added to a workflow."""
    return await workflow_client.list_available_step_types()


@router.get(
    "/available-trigger-types",
    response_model=List[TriggerTypeResponse],
    summary="List available trigger types",
)
async def get_available_trigger_types() -> List[TriggerTypeResponse]:
    """Returns a list of available trigger types that can be added to a workflow."""
    logger.info("Fetching available trigger types from workflow_client")
    try:
        trigger_types = await workflow_client.list_available_trigger_types()
        logger.info(f"Successfully fetched trigger types: {trigger_types}")
        return trigger_types
    except Exception as e:
        logger.error(f"Error fetching trigger types: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Error fetching available trigger types."
        )


@router.post(
    "/{workflow_uuid}/trigger",
    response_model=WorkflowModel,
    summary="Set trigger for a workflow",
)
async def set_workflow_trigger(
    workflow_uuid: UUID,
    request: SetTriggerRequest,
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Creates and attaches a trigger to the workflow.
    """
    logger.info(f"POST /workflows/{workflow_uuid}/trigger - Setting trigger")
    try:
        workflow = await workflow_client.set_trigger(
            workflow_uuid=workflow_uuid,
            trigger_type_id=request.trigger_type_id,
            user_id=user_id
        )
        logger.info(f"POST /workflows/{workflow_uuid}/trigger - Trigger set successfully")
        return workflow

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"POST /workflows/{workflow_uuid}/trigger - Error setting trigger: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error setting workflow trigger.")


@router.delete(
    "/{workflow_uuid}/trigger",
    response_model=WorkflowModel,
    summary="Remove trigger from a workflow",
)
async def remove_workflow_trigger(
    workflow_uuid: UUID,
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Removes the trigger from the workflow.
    """
    logger.info(f"DELETE /workflows/{workflow_uuid}/trigger - Removing trigger")
    try:
        workflow = await workflow_client.remove_trigger(
            workflow_uuid=workflow_uuid,
            user_id=user_id
        )
        logger.info(f"DELETE /workflows/{workflow_uuid}/trigger - Trigger removed successfully")
        return workflow

    except Exception as e:
        logger.error(f"DELETE /workflows/{workflow_uuid}/trigger - Error removing trigger: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error removing workflow trigger.") 
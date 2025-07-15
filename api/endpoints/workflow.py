import logging
import os
from typing import Any, Dict, List, Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, status

import workflow.client as workflow_client
import workflow.trigger_client as trigger_client
import workflow.internals.runner as runner
from workflow.models import (
    StepOutputData,
    WorkflowInstanceModel,
    WorkflowModel,
    WorkflowWithDetails,
    WorkflowStep,
)

from ..types.api_models.workflow import (
    AddStepRequest,
    CreateWorkflowRequest,
    SetTriggerRequest,
    TriggerTypeResponse,
    UpdateStepRequest,
    UpdateTriggerRequest,
)
from .auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["Workflows"])

# A simple cache for the LLM models to avoid reading the file on every request
llm_models_cache = None

@router.get("/available-llm-models", response_model=List[Dict[str, Any]])
async def get_available_llm_models():
    """
    Returns a list of available LLM models from the configuration file.
    """
    global llm_models_cache
    if llm_models_cache is None:
        try:
            with open("shared/llm_models.json", "r") as f:
                llm_models_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Could not load or parse llm_models.json: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Could not load available LLM models.")
    return llm_models_cache

@router.get("/available-tools", response_model=List[Dict[str, Any]])
async def get_available_tools():
    """
    Discovers and returns a list of all available tools from connected MCP servers.
    """
    try:
        tools = await workflow_client.discover_mcp_tools()
        return tools
    except Exception as e:
        logger.error(f"Could not discover MCP tools: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not discover available tools.")


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
    logger.info(f"[Worker: {os.getpid()}] GET /workflows/{workflow_uuid}")
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
# Step Management Endpoints
#
@router.put(
    "/steps/{step_uuid}",
    response_model=WorkflowStep,
    summary="Update a workflow step",
)
async def update_workflow_step(
    step_uuid: UUID,
    request: UpdateStepRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Updates the definition of a specific workflow step.
    The step is identified by its UUID, and the entire updated step object
    is passed in the request body.
    """
    logger.info(f"PUT /workflows/steps/{step_uuid}")
    
    # The UUID in the path takes precedence over the one in the body.
    if step_uuid != request.uuid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The UUID in the URL path does not match the UUID in the request body.",
        )

    try:
        updated_step = await workflow_client.update_step(
            step=request, user_id=user_id
        )
        if not updated_step:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Step not found"
            )
        return updated_step
    except Exception as e:
        logger.error(f"Error updating step {step_uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating workflow step.")


@router.post(
    "/{workflow_uuid}/steps",
    response_model=WorkflowWithDetails,
    summary="Add a new step to a workflow",
)
async def add_workflow_step(
    workflow_uuid: UUID,
    request: AddStepRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Adds a new step definition to the end of a workflow."""
    logger.info(f"[Worker: {os.getpid()}] POST /workflows/{workflow_uuid}/steps - Type: {request.step_type}, Name: {request.name}")
    try:
        await workflow_client.add_new_step(
            workflow_uuid=workflow_uuid,
            step_type=request.step_type,
            name=request.name,
            user_id=user_id,
        )
        # Return the full, updated workflow object
        logger.info(f"[Worker: {os.getpid()}] Step added, fetching details for {workflow_uuid}")
        return await workflow_client.get_with_details(
            workflow_uuid=workflow_uuid, user_id=user_id
        )
    except Exception as e:
        logger.error(f"Error adding step to workflow {workflow_uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error adding step to workflow.")


@router.delete(
    "/{workflow_uuid}/steps/{step_uuid}",
    response_model=WorkflowWithDetails,
    summary="Remove a step from a workflow",
)
async def remove_workflow_step(
    workflow_uuid: UUID,
    step_uuid: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Removes a step from a workflow and deletes the step definition.
    Returns the updated workflow.
    """
    logger.info(f"DELETE /workflows/{workflow_uuid}/steps/{step_uuid}")
    try:
        # The client function handles both removing the reference
        # and deleting the step definition.
        await workflow_client.delete_step(
            workflow_uuid=workflow_uuid,
            step_uuid=step_uuid,
            user_id=user_id,
        )

        # Return the full, updated workflow object
        logger.info(f"Step {step_uuid} removed, fetching updated details for {workflow_uuid}")
        return await workflow_client.get_with_details(
            workflow_uuid=workflow_uuid, user_id=user_id
        )
    except Exception as e:
        logger.error(f"Error removing step {step_uuid} from workflow {workflow_uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error removing step from workflow.")


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
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Creates and executes a new instance of a workflow.

    This endpoint accepts initial data (e.g., from a form or webhook)
    and uses it to kick off a new workflow run. The instance is created
    and its execution is scheduled to run in the background.
    """
    logger.info(f"POST /workflows/{workflow_uuid}/run - Kicking off workflow")
    try:
        # The client now handles both creating the instance and scheduling it.
        # We wrap the dict in a simple object to match StepOutputData structure.
        class TriggerData:
            def __init__(self, data):
                self.raw_data = data.get("raw_data")
                self.summary = data.get("summary")
                self.markdown_representation = data.get("markdown_representation")

        instance = await workflow_client.create_instance(
            workflow_uuid=workflow_uuid,
            triggering_data=TriggerData(triggering_data),
            user_id=user_id,
        )
        return instance
    except ValueError as e:
        logger.error(f"Error creating workflow instance: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred while running workflow {workflow_uuid}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An unexpected error occurred."
        )


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


#
# Trigger Management
#
@router.post(
    "/{workflow_uuid}/trigger",
    response_model=WorkflowWithDetails,
    summary="Set trigger for a workflow",
)
async def set_workflow_trigger(
    workflow_uuid: UUID,
    request: SetTriggerRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Creates and attaches a new trigger to the workflow. If a trigger already
    exists, it will be replaced.
    """
    await workflow_client.set_trigger(
        workflow_uuid=workflow_uuid,
        trigger_type_id=request.trigger_type_id,
        user_id=user_id,
    )
    return await workflow_client.get_with_details(
        workflow_uuid=workflow_uuid, user_id=user_id
    )


@router.delete(
    "/{workflow_uuid}/trigger",
    response_model=WorkflowWithDetails,
    summary="Remove trigger from a workflow",
)
async def remove_workflow_trigger(
    workflow_uuid: UUID, user_id: UUID = Depends(get_current_user_id)
):
    """Detaches and deletes the trigger associated with the workflow."""
    await workflow_client.remove_trigger(workflow_uuid=workflow_uuid, user_id=user_id)
    return await workflow_client.get_with_details(
        workflow_uuid=workflow_uuid, user_id=user_id
    )


@router.put(
    "/{workflow_uuid}/trigger",
    response_model=WorkflowWithDetails,
    summary="Update trigger settings for a workflow",
)
async def update_workflow_trigger(
    workflow_uuid: UUID,
    request: UpdateTriggerRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Updates the settings of an existing trigger for a workflow.
    """
    logger.info(f"PUT /workflows/{workflow_uuid}/trigger - Received request body: {request.dict()}")
    # Get the current trigger for the workflow
    trigger = await trigger_client.get_for_workflow(
        workflow_uuid=workflow_uuid, user_id=user_id
    )
    if not trigger:
        logger.error(f"No trigger found for workflow {workflow_uuid}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="No trigger found for this workflow"
        )
    
    # Update the trigger's filter rules
    logger.info(f"Updating trigger {trigger.uuid} with filter rules: {request.filter_rules}")
    trigger.filter_rules = request.filter_rules
    
    # Save the updated trigger
    await trigger_client.update(trigger_model=trigger, user_id=user_id)
    
    # Return the updated workflow with details
    logger.info(f"Successfully updated trigger for workflow {workflow_uuid}")
    return await workflow_client.get_with_details(
        workflow_uuid=workflow_uuid, user_id=user_id
    ) 
import logging
import os
from typing import Any, Dict, List, Optional
from uuid import UUID
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Request
from pydantic import BaseModel

import workflow.client as workflow_client
import workflow.trigger_client as trigger_client
import workflow.internals.runner as runner
from workflow_agent.client import client as workflow_agent_client
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
    CreateFromTemplateRequest,
)
from workflow_agent.client.models import ChatMessage, ChatRequest, ChatStepResponse
from .auth import get_current_user_id
from agentlogger.src.client import upsert_log_entry_sync, get_log_entry
from agentlogger.src.models import LogEntry, Message as LoggerMessage


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["Workflows"])
WORKFLOW_TEMPLATES_DIR = "api/workflow_templates"


class TemplateInfo(BaseModel):
    id: str
    name: str
    description: str


class WorkflowFromTemplateResponse(BaseModel):
    workflow: WorkflowModel
    workflow_start_message: Optional[str] = None


class UpdateWorkflowStatusRequest(BaseModel):
    is_active: bool

class UpdateWorkflowDetailsRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

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


@router.get("/templates", response_model=List[TemplateInfo])
async def list_workflow_templates():
    """
    Lists all available workflow templates from the template directory.
    """
    logger.info("GET /workflows/templates - Listing all workflow templates")
    if not os.path.isdir(WORKFLOW_TEMPLATES_DIR):
        logger.warning(f"Workflow templates directory not found at {WORKFLOW_TEMPLATES_DIR}")
        return []
    
    templates = []
    for f in os.listdir(WORKFLOW_TEMPLATES_DIR):
        if f.endswith(".json"):
            try:
                with open(os.path.join(WORKFLOW_TEMPLATES_DIR, f), "r") as template_file:
                    data = json.load(template_file)
                    templates.append(TemplateInfo(
                        id=f.replace(".json", ""),
                        name=data.get("name", "Unnamed Template"),
                        description=data.get("description", "No description available.")
                    ))
            except Exception as e:
                logger.error(f"Error reading or parsing template file {f}: {e}")

    logger.info(f"GET /workflows/templates - Found {len(templates)} templates.")
    return templates


@router.post("/from-template", response_model=WorkflowFromTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow_from_template(request: CreateFromTemplateRequest, user_id: UUID = Depends(get_current_user_id)):
    """
    Creates a new workflow from a specified template.
    """
    logger.info(f"POST /workflows/from-template - Creating workflow from template '{request.template_id}'")
    try:
        template_path = os.path.join(WORKFLOW_TEMPLATES_DIR, f"{request.template_id}.json")
        if not os.path.isfile(template_path):
            logger.error(f"Template file not found at {template_path}")
            raise HTTPException(status_code=404, detail=f"Template with ID '{request.template_id}' not found.")

        with open(template_path, 'r') as f:
            template_data = json.load(f)
        
        workflow_start_message = template_data.get("workflow_start_message")

        new_workflow = await workflow_client.create(
            name=template_data["name"],
            description=template_data["description"],
            user_id=user_id
        )
        
        return WorkflowFromTemplateResponse(
            workflow=new_workflow,
            workflow_start_message=workflow_start_message
        )
    except Exception as e:
        logger.error(f"POST /workflows/from-template - Error creating workflow from template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error creating workflow from template.")


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


@router.patch("/{workflow_uuid}", response_model=WorkflowModel, summary="Update workflow details")
async def update_workflow_details(
    workflow_uuid: UUID,
    request: UpdateWorkflowDetailsRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Updates a workflow's details, such as its name or description."""
    updated_workflow = await workflow_client.update_workflow_details(
        workflow_uuid=workflow_uuid,
        name=request.name,
        description=request.description,
        user_id=user_id,
    )
    if not updated_workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found"
        )
    return updated_workflow


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


@router.put(
    "/{workflow_uuid}/status",
    response_model=WorkflowModel,
    summary="Update the status of a workflow",
)
async def update_workflow_status(
    workflow_uuid: UUID,
    request: UpdateWorkflowStatusRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Updates the active status of a workflow (e.g., to pause or resume it).
    """
    updated_workflow = await workflow_client.set_active_status(
        workflow_uuid=workflow_uuid, is_active=request.is_active, user_id=user_id
    )
    if not updated_workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found"
        )
    return updated_workflow


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

#
# Workflow Agent Chat Endpoints
#
@router.post(
    "/{workflow_uuid}/chat/step",
    response_model=ChatStepResponse,
    summary="Execute a single step in a workflow agent chat",
    tags=["Workflow Agent"],
)
async def workflow_agent_chat_step(
    workflow_uuid: UUID,
    request: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Runs a single step of the workflow agent chat.
    """
    try:
        chat_response = await workflow_agent_client.run_chat_step(
            request=request, user_id=user_id, workflow_uuid=workflow_uuid
        )

        # --- Add Logging ---
        try:
            workflow = await workflow_client.get(uuid=workflow_uuid, user_id=user_id)
            
            existing_log = get_log_entry(request.conversation_id)
            start_time = existing_log.start_time if existing_log else datetime.now(timezone.utc)
            end_time = datetime.now(timezone.utc) if chat_response.is_complete else None

            logger_messages = [LoggerMessage.model_validate(msg.model_dump()) for msg in chat_response.messages]

            log_entry = LogEntry(
                id=request.conversation_id,
                log_type='workflow_agent',
                workflow_id=str(workflow_uuid),
                workflow_name=workflow.name if workflow else "Workflow Configuration Agent",
                step_instance_id=request.conversation_id,
                step_name="Workflow Configuration Agent Chat",
                messages=logger_messages,
                start_time=start_time,
                end_time=end_time,
            )
            upsert_log_entry_sync(log_entry)
        except Exception as e:
            logger.error(f"Failed to log workflow agent turn for conversation {request.conversation_id}: {e}", exc_info=True)
        # --- End Logging ---
        
        return chat_response
    except Exception as e:
        logger.error(f"Error during agent chat step for workflow {workflow_uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred during the agent chat turn.") 


@router.post(
    "/{workflow_uuid}/chat/submit_human_input",
    response_model=ChatStepResponse,
    summary="Submit user input and resume a paused workflow agent chat",
    tags=["Workflow Agent"],
)
async def submit_human_input(
    workflow_uuid: UUID,
    submission: Dict[str, Any], # The frontend will send the raw submission object
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Receives user input from the frontend form, packages it into the
    `human_input` field of a standard ChatRequest, and sends it to the
    unified `run_chat_step` function to continue the conversation.
    """
    # Reconstruct the ChatRequest, placing the user's submission
    # into the new `human_input` field.
    chat_request = ChatRequest(
        conversation_id=submission['conversation_id'],
        messages=[ChatMessage(**msg) for msg in submission['messages']],
        human_input={
            "tool_call_id": submission['tool_call_id'],
            "user_input": submission['user_input'],
        }
    )

    return await workflow_agent_client.run_chat_step(
        request=chat_request, user_id=user_id, workflow_uuid=workflow_uuid
    ) 
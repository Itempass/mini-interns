from pydantic import BaseModel
from typing import Dict, Any
from workflow.models import CustomAgent, CustomLLM, StopWorkflowChecker, RAGStep


class CreateWorkflowRequest(BaseModel):
    """Request model for creating a new workflow."""

    name: str
    description: str


class TriggerTypeResponse(BaseModel):
    """Response model for available trigger types."""

    id: str
    name: str
    description: str
    initial_data_description: str


class SetTriggerRequest(BaseModel):
    """Request model for setting a trigger on a workflow."""

    trigger_type_id: str


class UpdateTriggerRequest(BaseModel):
    """Request model for updating trigger settings."""
    
    filter_rules: Dict[str, Any]


class AddStepRequest(BaseModel):
    step_type: str
    name: str


UpdateStepRequest = CustomLLM | CustomAgent | StopWorkflowChecker | RAGStep 


class CreateFromTemplateRequest(BaseModel):
    template_id: str
from pydantic import BaseModel


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
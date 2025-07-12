from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# 4.1. Workflow and Step Definitions
class StopWorkflowCondition(BaseModel):
    """Defines a rule to evaluate against a step's output."""

    step_definition_uuid: UUID  # The step whose output to inspect
    extraction_json_path: str  # JSONPath to extract value from the step's raw_data
    operator: Literal["equals", "not_equals", "contains", "greater_than", "less_than"]
    target_value: Any


class CustomLLM(BaseModel):
    """A workflow step definition that calls an LLM without tools."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A unique, user-defined name for this step.")
    description: str = Field(default="", description="A description of what this step does.")
    type: Literal["custom_llm"] = "custom_llm"
    model: str
    system_prompt: str
    generated_summary: Optional[str] = None  # For UI display, auto-generated


class CustomAgent(BaseModel):
    """A workflow step definition that uses an LLM with tools."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A unique, user-defined name for this step.")
    description: str = Field(default="", description="A description of what this step does.")
    type: Literal["custom_agent"] = "custom_agent"
    model: str
    system_prompt: str
    tools: Dict[str, Any] = Field(default_factory=dict)  # tool_id -> { enabled: bool, ... }
    generated_summary: Optional[str] = None  # For UI display, auto-generated


class StopWorkflowChecker(BaseModel):
    """A step that checks conditions to stop the workflow based on data from previous steps."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A unique, user-defined name for this step.")
    description: str = Field(default="", description="A description of what this step does.")
    type: Literal["stop_checker"] = "stop_checker"
    stop_conditions: List[StopWorkflowCondition] = Field(...)
    # This step does not produce output for other steps to consume.


WorkflowStep = Union[CustomLLM, CustomAgent, StopWorkflowChecker]


class WorkflowModel(BaseModel):
    """The definition of a workflow."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str
    description: str
    is_active: bool = True
    trigger_uuid: Optional[UUID] = None
    steps: List[UUID] = Field(default_factory=list, description="An ordered list of Step UUIDs referenced by their unique IDs.")
    template_id: Optional[str] = None
    template_version: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TriggerModel(BaseModel):
    """Defines what initiates a workflow."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_uuid: UUID
    filter_rules: Dict[str, Any] = Field(default_factory=dict)
    initial_data_description: str = Field(..., description="Description of the initial data passed to the workflow.")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# 4.2. Instance and Execution Models
class MessageModel(BaseModel):
    """Individual message in a conversation, used for logging and debugging."""

    content: Optional[str] = None
    role: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    model_config = {"extra": "allow"}


class StepOutputData(BaseModel):
    """A standard, self-contained, and addressable unit of data produced by a workflow step."""

    uuid: UUID = Field(default_factory=uuid4)  # A globally unique ID for this specific piece of data.
    raw_data: Any
    summary: Optional[str] = None
    markdown_representation: Optional[str] = None


class CustomLLMInstanceModel(BaseModel):
    """An instance of a CustomLLM step execution."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_instance_uuid: UUID
    status: Literal["pending", "running", "completed", "failed", "skipped", "cancelled"]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    llm_definition_uuid: UUID  # Link back to CustomLLM definition
    messages: List[MessageModel] = Field(default_factory=list)
    input_data: Optional[Dict[str, Any]] = None
    output: Optional[StepOutputData] = None  # The full output data object.


class CustomAgentInstanceModel(BaseModel):
    """An instance of a CustomAgent step execution."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_instance_uuid: UUID
    status: Literal["pending", "running", "completed", "failed", "skipped", "cancelled"]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    agent_definition_uuid: UUID  # Link back to CustomAgent definition
    messages: List[MessageModel] = Field(default_factory=list)
    input_data: Optional[Dict[str, Any]] = None
    output: Optional[StepOutputData] = None  # The full output data object.


class StopWorkflowCheckerInstanceModel(BaseModel):
    """An instance of a StopWorkflowChecker step execution."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_instance_uuid: UUID
    status: Literal["pending", "running", "completed", "failed", "skipped", "cancelled"]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    checker_definition_uuid: UUID  # Link back to StopWorkflowChecker definition
    input_data: Optional[Dict[str, Any]] = None
    # This step does not produce an output


WorkflowStepInstance = Union[CustomLLMInstanceModel, CustomAgentInstanceModel, StopWorkflowCheckerInstanceModel]


class WorkflowInstanceModel(BaseModel):
    """An instance of an executed workflow."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_definition_uuid: UUID
    status: Literal["running", "completed", "stopped", "failed", "cancelled"]
    trigger_output: Optional[StepOutputData] = None  # The initial data that started the workflow.
    step_instances: List[WorkflowStepInstance] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# 4.3. API Response Models
class WorkflowWithDetails(BaseModel):
    """A fully hydrated workflow model for frontend consumption."""

    uuid: UUID
    user_id: UUID
    name: str
    description: str
    is_active: bool
    trigger: Optional[TriggerModel] = None
    steps: List[WorkflowStep] = []
    template_id: Optional[str] = None
    template_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime 
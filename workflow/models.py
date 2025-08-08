from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


# 4.1. Workflow and Step Definitions
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StopWorkflowChecker(BaseModel):
    """A step that checks conditions to stop the workflow based on data from previous steps."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A unique, user-defined name for this step.")
    description: str = Field(default="", description="A description of what this step does.")
    type: Literal["stop_checker"] = "stop_checker"
    step_to_check_uuid: Optional[UUID] = None # The step whose output to inspect
    check_mode: Literal["stop_if_output_contains", "continue_if_output_contains"] = "stop_if_output_contains"
    match_values: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # This step does not produce output for other steps to consume.


class CheckerResult(BaseModel):
    """The result of a StopWorkflowChecker execution."""
    should_stop: bool
    reason: str
    evaluated_input: str


class RAGStep(BaseModel):
    """A workflow step that performs retrieval-augmented generation over a vector database."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A unique, user-defined name for this step.")
    description: str = Field(default="", description="A description of what this step does.")
    type: Literal["rag"] = "rag"
    system_prompt: str = Field(..., description="The query or prompt used to search and ground the response.")
    vectordb_uuid: UUID = Field(..., description="The UUID of the configured vector database to use.")
    rerank: bool = Field(default=False, description="Whether to apply reranking to retrieved documents.")
    top_k: int = Field(default=5, description="The number of results to return (and optionally rerank).")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


WorkflowStep = Union[CustomLLM, CustomAgent, StopWorkflowChecker, RAGStep]


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TriggerModel(BaseModel):
    """Defines what initiates a workflow."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_uuid: UUID
    filter_rules: Dict[str, Any] = Field(default_factory=dict)
    initial_data_description: str = Field(..., description="Description of the initial data passed to the workflow.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# 4.2. Instance and Execution Models
class StepOutputData(BaseModel):
    """
    A container for the output data of a single workflow step.
    Each step's output is stored in one of these objects.
    """
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    markdown_representation: str # A markdown representation of the data.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class InitialWorkflowData(BaseModel):
    """
    The initial data that a workflow instance is created with.
    This data comes from the trigger.
    """
    markdown_representation: str

class MessageModel(BaseModel):
    """Individual message in a conversation, used for logging and debugging."""

    content: Optional[str] = None
    role: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    model_config = {"extra": "allow"}


class CustomLLMInstanceModel(BaseModel):
    """An instance of a CustomLLM step execution."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_instance_uuid: UUID
    status: Literal["pending", "running", "completed", "failed", "skipped", "cancelled"]
    started_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
    started_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
    started_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    checker_definition_uuid: UUID  # Link back to StopWorkflowChecker definition
    input_data: Optional[Dict[str, Any]] = None
    # This step does not produce an output


# --- New: RAG Step Instance ---
class RAGStepInstanceModel(BaseModel):
    """An instance of a RAG step execution."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_instance_uuid: UUID
    status: Literal["pending", "running", "completed", "failed", "skipped", "cancelled"]
    started_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rag_definition_uuid: UUID  # Link back to RAGStep definition
    messages: List[MessageModel] = Field(default_factory=list)
    input_data: Optional[Dict[str, Any]] = None
    output: Optional[StepOutputData] = None


WorkflowStepInstance = Union[CustomLLMInstanceModel, CustomAgentInstanceModel, StopWorkflowCheckerInstanceModel, RAGStepInstanceModel]


class WorkflowInstanceModel(BaseModel):
    """An instance of an executed workflow."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_definition_uuid: UUID
    status: Literal["running", "completed", "stopped", "failed", "cancelled"]
    trigger_output: Optional[StepOutputData] = None  # The initial data that started the workflow.
    step_instances: List[WorkflowStepInstance] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None


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
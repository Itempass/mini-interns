# 2025-07-16: Workflow Engine Implementation Plan

## 1. High-Level Overview

This document outlines a plan to refactor the current agent system into a more powerful and flexible "Workflow Engine". The goal is to allow users to chain together different processing steps to create complex, automated sequences.

A **Workflow** is a linear sequence of steps that are executed in order. It is initiated by a **Trigger**. Each step in the workflow can consume data from any of the previous steps and produce its own output. This output is stored in a `DataContainerInstanceModel`, which can then be referenced by subsequent steps.

The initial implementation will focus on a strictly linear chain of execution.

## 2. Core Concepts

-   **Workflow**: The definition of a multi-step process. It ties together a trigger and a sequence of step definitions.
-   **Workflow Step (Definition)**: A single unit of work within a workflow. We have three types: `CustomLLM`, `CustomAgent`, and `StopWorkflowChecker`.
-   **DataContainerModel**: A definition (or "type") of a piece of data that can be produced by a workflow step.
-   **Trigger**: An event listener that initiates a workflow. It applies simple filtering rules and, upon a match, starts a `WorkflowInstanceModel`, providing the initial data.
-   **WorkflowInstanceModel**: An instance of a running or completed workflow. It contains the list of all the specific step instances (`CustomLLMInstanceModel`, etc.) from that run.
-   **DataContainerInstanceModel**: An instance of a `DataContainerModel`, holding the actual output produced by a step during a specific `WorkflowInstanceModel`.
-   **Step Instance Models** (`CustomLLMInstanceModel`, `CustomAgentInstanceModel`, etc.): A record of a single execution of a step definition within a `WorkflowInstanceModel`. It stores the status, timestamps, and results of that specific run.

## 3. Data Flow and Referencing

Data flows sequentially through the workflow, with the output of one step becoming the potential input for any subsequent step. The concept of a separate "Data Container" is removed; instead, a step's output is stored directly within the instance of that step.

To use the output of a previous step or the initial trigger data, a placeholder referencing the **Step Definition UUID** is used. The syntax is `<<step_output.{step_definition_uuid}>>` for step outputs, and `<<trigger_output>>` for the initial data.

**Example:**
-   Step 1 ("Summarizer") has definition UUID `summarizer_uuid`. It produces a summary.
-   Step 2's prompt would be: `"Label this summary: <<step_output.summarizer_uuid>>"`

This referencing is handled by the UI. The user selects a previous step from a dropdown, and the UI inserts the correct placeholder. The workflow engine is then responsible for looking up the correct step instance from the current run and injecting the appropriate data format at runtime.

## 4. Pydantic Models

Below are the proposed Pydantic models for the new workflow structure.

### 4.1. Workflow and Step Definitions

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Union, Optional
from uuid import UUID, uuid4
from datetime import datetime

class StopWorkflowCondition(BaseModel):
    """Defines a rule to evaluate against a step's output."""
    step_definition_uuid: UUID # The step whose output to inspect
    extraction_json_path: str # JSONPath to extract value from the step's raw_data
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
    generated_summary: Optional[str] = None # For UI display, auto-generated
    
class CustomAgent(BaseModel):
    """A workflow step definition that uses an LLM with tools."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A unique, user-defined name for this step.")
    description: str = Field(default="", description="A description of what this step does.")
    type: Literal["custom_agent"] = "custom_agent"
    model: str
    system_prompt: str
    tools: Dict[str, Any] = Field(default_factory=dict) # tool_id -> { enabled: bool, ... }
    generated_summary: Optional[str] = None # For UI display, auto-generated

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
    trigger_uuid: UUID
    steps: List[UUID] = Field(default_factory=list, description="An ordered list of Step UUIDs referenced by their unique IDs.")
    template_id: Optional[str] = None
    template_version: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class TriggerModel(BaseModel):
    """Defines what initiates a workflow."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_uuid: UUID
    filter_rules: Dict[str, Any] = Field(default_factory=dict)
    initial_data_description: str = Field(..., description="Description of the initial data passed to the workflow.")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### 4.2. Instance and Execution Models

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal, Union
from uuid import UUID, uuid4
from datetime import datetime

class MessageModel(BaseModel):
    """Individual message in a conversation, used for logging and debugging."""
    content: Optional[str] = None
    role: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    model_config = {"extra": "allow"}

class StepOutputData(BaseModel):
    """A standard, self-contained, and addressable unit of data produced by a workflow step."""
    uuid: UUID = Field(default_factory=uuid4) # A globally unique ID for this specific piece of data.
    raw_data: Any
    summary: Optional[str] = None
    markdown_representation: Optional[str] = None

class CustomLLMInstanceModel(BaseModel):
    """An instance of a CustomLLM step execution."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_instance_uuid: UUID
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    llm_definition_uuid: UUID # Link back to CustomLLM definition
    messages: List[MessageModel] = Field(default_factory=list)
    input_data: Optional[Dict[str, Any]] = None
    output: Optional[StepOutputData] = None # The full output data object.
    
class CustomAgentInstanceModel(BaseModel):
    """An instance of a CustomAgent step execution."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_instance_uuid: UUID
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    agent_definition_uuid: UUID # Link back to CustomAgent definition
    messages: List[MessageModel] = Field(default_factory=list)
    input_data: Optional[Dict[str, Any]] = None
    output: Optional[StepOutputData] = None # The full output data object.

class StopWorkflowCheckerInstanceModel(BaseModel):
    """An instance of a StopWorkflowChecker step execution."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_instance_uuid: UUID
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    checker_definition_uuid: UUID # Link back to StopWorkflowChecker definition
    input_data: Optional[Dict[str, Any]] = None
    # This step does not produce an output

WorkflowStepInstance = Union[CustomLLMInstanceModel, CustomAgentInstanceModel, StopWorkflowCheckerInstanceModel]

class WorkflowInstanceModel(BaseModel):
    """An instance of an executed workflow."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_definition_uuid: UUID
    status: Literal["running", "completed", "stopped", "failed"]
    trigger_output: Optional[StepOutputData] = None # The initial data that started the workflow.
    step_instances: List[WorkflowStepInstance] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### 4.3. API Response Models

The following models are used for API responses and do not necessarily map directly to database tables. They are designed to provide the frontend with all the necessary data in a single call.

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal, Union
from uuid import UUID, uuid4
from datetime import datetime

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
```

## 5. Client Methods

The public API for managing workflows will be organized into a series of decoupled client modules within a new `workflow` directory. This pattern follows the existing structure of `agent/client.py` to ensure a consistent, Pythonic developer experience where logic is grouped by the domain model it operates on.

### 5.1. Design Philosophy

The client methods are designed around an **Orchestration Facade** pattern.

-   **`workflow/client.py` (The Facade):** This is the primary entry point for any application logic that needs to make *structural* changes to a workflow. It handles high-level actions like adding a new step (`add_new_step`) or setting the trigger (`set_trigger`). Its methods orchestrate the necessary calls to other clients and are designed to always return the complete, updated `WorkflowModel` to simplify frontend state management.

-   **Step & Trigger Clients (The Standalone Managers):** Modules like `llm_client.py`, `agent_client.py`, and `trigger_client.py` are responsible for the direct `create`, `get`, `save`, and `delete` operations on their respective data models. While they are primarily called by the workflow facade, they can be used directly for more granular updates, such as modifying a step's `system_prompt` without changing the workflow's structure.

This design provides a simple, high-level API for common operations while retaining a clean, decoupled architecture on the backend.

### 5.2. Proposed File Structure

```
workflow/
├── __init__.py
├── client.py               # Handles WorkflowModel and WorkflowInstanceModel logic
├── llm_client.py           # Handles CustomLLM and CustomLLMInstanceModel logic
├── agent_client.py         # Handles CustomAgent and CustomAgentInstanceModel logic
├── checker_client.py       # Handles StopWorkflowChecker and StopWorkflowCheckerInstanceModel logic
├── trigger_client.py       # Handles TriggerModel logic
├── models.py               # Contains all the Pydantic models
└── internals/
    ├── __init__.py
    ├── database.py         # Handles direct database interactions for all workflow models.
    ├── output_processor.py   # Helper to create and summarize step output data.
    └── runner.py           # Handles the execution logic for workflow steps.
```

### 5.3. Functions by Module

The following functions represent the Pythonic interface for an application to interact with the workflow system.

#### `workflow/client.py` (The Orchestration Facade)

*   **Definition Management**
    *   `async def create(name: str, description: str) -> WorkflowModel:` Creates a new, empty workflow.
    *   `async def get(uuid: UUID) -> Optional[WorkflowModel]:` Retrieves a workflow definition.
    *   `async def get_with_details(workflow_uuid: UUID) -> Optional[WorkflowWithDetails]:` Retrieves a single, "hydrated" workflow object with all its step and trigger objects fully populated. This is the primary method for fetching workflow data for a UI.
    *   `async def list() -> List[WorkflowModel]:` Lists all workflow definitions.
    *   `async def delete(uuid: UUID) -> None:` Deletes a workflow definition. This will orchestrate the deletion of the workflow itself, its associated trigger, and all of its step definitions to prevent orphaned data.
*   **Structure Management**
    *   `async def add_new_step(workflow_uuid: UUID, step_type: Literal["custom_llm", "custom_agent", "stop_checker"], name: str, position: int = -1) -> WorkflowModel:` Creates a new step definition and adds its reference to the workflow, returning the updated `WorkflowModel`. This is the primary method for adding steps.
    *   `async def delete_step(workflow_uuid: UUID, step_uuid: UUID) -> None:` Removes a step from a workflow's `steps` list and deletes the step definition itself. Internally, this will remove the reference from the workflow, determine the step's type, and then call the appropriate client (e.g., `llm_client.delete(step_uuid)`) to delete the definition.
    *   `async def reorder_steps(workflow_uuid: UUID, ordered_step_uuids: List[UUID]) -> WorkflowModel:` Reorders the `steps` list of a workflow.
    *   `async def set_trigger(workflow_uuid: UUID, trigger_type_id: str) -> WorkflowModel:` Creates and attaches a new trigger to the workflow based on a selected type. It orchestrates the creation via the `trigger_client` and returns the updated `WorkflowModel`.
    *   `async def remove_trigger(workflow_uuid: UUID) -> WorkflowModel:` Detaches and deletes the trigger associated with the workflow, returning the updated `WorkflowModel`.
*   **Execution Management**
    *   `async def create_instance(workflow_uuid: UUID, triggering_data: Any) -> WorkflowInstanceModel:` Manually starts a run of a workflow.
    *   `async def get_instance(instance_uuid: UUID) -> Optional[WorkflowInstanceModel]:` Retrieves the status and results of a workflow run.
    *   `async def get_output_data(output_id: UUID) -> Optional[StepOutputData]:` Retrieves a `StepOutputData` object using its unique ID. This provides the primary internal method for fetching the full, uncompressed result of any step.
    *   `async def list_instances(workflow_uuid: UUID) -> List[WorkflowInstanceModel]:` Lists all runs for a given workflow.
    *   `async def cancel_instance(instance_uuid: UUID) -> None:` Cancels a running workflow.
*   **Utility Functions**
    *   `async def list_available_step_types() -> List[Dict[str, Any]]:` Returns a list of all available step types that can be added to a workflow, allowing the frontend to dynamically display creation options. To keep it simple for now, we can just hardcode a return statement that has a list with dicts, each dict has a type, name and description.
    *   `async def list_available_trigger_types() -> List[Dict[str, Any]]:` Returns a list of all available trigger types that can be added to a workflow. This is a pass-through from the `trigger_client`.
    *   `async def discover_mcp_tools() -> List[Dict[str, Any]]:` Discovers all available tools from all connected MCP servers. This is a pass-through from the `agent_client`.

#### `workflow/llm_client.py` (Standalone Manager for `CustomLLM` Steps)

*   **Definition Management**
    *   `async def create(name: str, model: str, system_prompt: str) -> CustomLLM:` Creates a new, standalone `CustomLLM` step definition. This is primarily called by the `workflow_client` facade.
    *   `async def get(uuid: UUID) -> Optional[CustomLLM]:` Retrieves a `CustomLLM` step definition.
    *   `async def save(llm_model: CustomLLM) -> CustomLLM:` Saves the state of a `CustomLLM` step.
    *   `async def delete(uuid: UUID) -> None:` Deletes a CustomLLM step definition.
*   **Instance Management**
    *   `async def create_instance(workflow_instance_uuid: UUID, llm_definition_uuid: UUID, user_id: UUID) -> CustomLLMInstanceModel:` Creates the record for a new `CustomLLMInstanceModel` run, typically with a `pending` status. Called by the workflow runner.
    *   `async def save_instance(instance: CustomLLMInstanceModel) -> CustomLLMInstanceModel:` Updates the state of a `CustomLLMInstanceModel` during and after execution.

#### `workflow/agent_client.py` (Standalone Manager for `CustomAgent` Steps)

*   **Tool Discovery**
    *   `async def discover_mcp_tools() -> List[Dict[str, Any]]:` Contains the logic for discovering all available tools from all connected MCP servers. This logic will be migrated from the old `agent/client.py`.
*   **Definition Management**
    *   `async def create(name: str, model: str, system_prompt: str) -> CustomAgent:` Creates a new, standalone `CustomAgent` step definition. This is primarily called by the `workflow_client` facade.
    *   `async def get(uuid: UUID) -> Optional[CustomAgent]:` Retrieves a `CustomAgent` step definition.
    *   `async def save(agent_model: CustomAgent) -> CustomAgent:` Saves the state of a `CustomAgent` step.
    *   `async def delete(uuid: UUID) -> None:` Deletes a CustomAgent step definition.
*   **Instance Management**
    *   `async def create_instance(workflow_instance_uuid: UUID, agent_definition_uuid: UUID, user_id: UUID) -> CustomAgentInstanceModel:` Creates the record for a new `CustomAgentInstanceModel` run, typically with a `pending` status. Called by the workflow runner.
    *   `async def save_instance(instance: CustomAgentInstanceModel) -> CustomAgentInstanceModel:` Updates the state of a `CustomAgentInstanceModel` during and after execution.

#### `workflow/checker_client.py` (Standalone Manager for `StopWorkflowChecker` Steps)

*   **Definition Management**
    *   `async def create(name: str, stop_conditions: List[StopWorkflowCondition]) -> StopWorkflowChecker:` Creates a new, standalone StopWorkflowChecker step definition. This is primarily called by the `workflow_client` facade.
    *   `async def get(uuid: UUID) -> Optional[StopWorkflowChecker]:` Retrieves a `StopWorkflowChecker` step definition.
    *   `async def save(checker_model: StopWorkflowChecker) -> StopWorkflowChecker:` Saves the state of a `StopWorkflowChecker` step.
    *   `async def delete(uuid: UUID) -> None:` Deletes a StopWorkflowChecker step definition.
*   **Instance Management**
    *   `async def create_instance(workflow_instance_uuid: UUID, checker_definition_uuid: UUID, user_id: UUID) -> StopWorkflowCheckerInstanceModel:` Creates the record for a new `StopWorkflowCheckerInstanceModel` run, typically with a `pending` status. Called by the workflow runner.
    *   `async def save_instance(instance: StopWorkflowCheckerInstanceModel) -> StopWorkflowCheckerInstanceModel:` Updates the state of a `StopWorkflowCheckerInstanceModel` during and after execution.

#### `workflow/trigger_client.py` (Standalone Manager for `TriggerModel`)

*   `async def get_available_types() -> List[Dict[str, Any]]:` Returns a list of available trigger types (e.g., from a JSON config) for the UI to display.
*   `async def create(workflow_uuid: UUID, trigger_type_id: str) -> TriggerModel:` Creates a new trigger instance with default settings for the given type. This is primarily called by the `workflow_client` facade.
*   `async def get(uuid: UUID) -> Optional[TriggerModel]:` Retrieves a trigger definition.
*   `async def get_for_workflow(workflow_uuid: UUID) -> Optional[TriggerModel]:` Retrieves the trigger for a specific workflow.
*   `async def list() -> List[TriggerModel]:` Lists all triggers.
*   `async def save(trigger_model: TriggerModel) -> TriggerModel:` Updates the state of a trigger.
*   `async def delete(uuid: UUID) -> None:` Deletes a trigger.

## 6. Execution Flow

The execution logic is divided between a central `WorkflowRunner`, specialized clients, and an `OutputProcessor`.

1.  **Trigger Fires**: An event (e.g., new email) matches a trigger's `filter_rules`.
2.  **Workflow Instance Creation**: The trigger system calls `workflow_client.create_instance`.
    - A `WorkflowInstanceModel` is created.
    - The trigger client calls a helper in `workflow/internals/output_processor.py` to process the initial event data into a `StepOutputData` object.
    - This `StepOutputData` object is saved to the `trigger_output` field of the `WorkflowInstanceModel`.
3.  **Runner Iterates Through Steps**: The `WorkflowRunner` begins executing the steps in order.
4.  **For each step, the Runner Prepares Input**:
    a. The runner inspects the step's `system_prompt` for placeholders like `<<step_output.{def_uuid}>>` or `<<trigger_output>>`.
    b. It determines the *type of step it is about to run* to decide the data format:
        - If the step is a `CustomAgent`, it retrieves the required `StepOutputData` but **dynamically creates a compressed JSON reference** containing the `output_id` and `summary`. This is injected into the agent's context.
        - If the step is a `CustomLLM`, it injects the full `raw_data` (or `markdown_representation`) from the `StepOutputData` object into the prompt.
5.  **Runner Delegates Execution to the Client**:
    a. The runner calls the appropriate client's execution method (e.g., `llm_client.execute(...)`).
    b. The client handles the core logic (e.g., calling the LLM API).
    c. After receiving the raw result, the client calls the `output_processor.create_output_data()` helper to generate a complete `StepOutputData` object (with a new UUID, summary, etc.).
    d. The client saves this `StepOutputData` object to the `output` field of the `WorkflowStepInstance` and populates the `output_id` column for fast lookups.
6.  **`StopWorkflowChecker` Evaluation**: If a step is a `StopWorkflowChecker`, its logic is evaluated. If a stop condition is met, the `WorkflowInstanceModel` status is set to `stopped`, and execution halts.
7.  **Workflow Completion**: Once all steps are completed, the `WorkflowInstanceModel` status is set to `completed`.

## 7. Backend Responsibilities

-   **API Endpoint for Data Fetching**: A new endpoint, `GET /api/v1/outputs/{output_id}`, will be created. This allows external services (like MCPs) to securely fetch the `raw_data` of any step's output using its unique ID.
-   **`generated_summary` Regeneration**: The API backend will be responsible for detecting changes to a step's `system_prompt` or `tools` during an `update_workflow` call. When a change is detected, it will trigger a background LLM call to regenerate the `generated_summary` field for that step.
-   **Asynchronous Execution**: The execution of a `WorkflowInstanceModel` should be handled by a background worker system (like Celery, ARQ, or Dramatiq) to avoid blocking API requests.

## 8. Database Layer

The persistence layer for the workflow engine will reside in `workflow/internals/database.py`. It will abstract all direct database interactions (e.g., SQL queries) away from the client-side logic, following the pattern established by `agent/internals/database.py`.

### 8.1. Proposed Table Structure (Hybrid Model)

Based on a hybrid approach that uses explicit columns for indexed metadata and JSON blobs for flexible configuration, the following tables are proposed. This schema does not include a local `users` table and assumes the `user_id` is provided by an external authentication system.

*   **`workflows`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `name` (Text)
    *   `description` (Text)
    *   `is_active` (Boolean)
    *   `trigger_uuid` (UUID, nullable)
    *   `steps` (JSON, array of `workflow_steps.uuid`s, maintains order)
    *   `created_at`, `updated_at`

*   **`workflow_steps`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `name` (Text)
    *   `type` (Text Discriminator: "custom_llm", "custom_agent", "stop_checker")
    *   `details` (JSON, for type-specific settings like `model`, `system_prompt`, `tools`, `stop_conditions`, etc.)
    *   `created_at`, `updated_at`

*   **`triggers`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `workflow_uuid` (UUID)
    *   `details` (JSON, for `filter_rules`, `initial_data_description`, etc.)
    *   `created_at`, `updated_at`

*   **`workflow_instances`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `workflow_definition_uuid` (UUID, points to `workflows.uuid`)
    *   `status` (Text: "running", "completed", etc.)
    *   `trigger_output` (JSON, stores a `StepOutputData` object)
    *   `created_at`, `updated_at`

*   **`workflow_step_instances`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `workflow_instance_uuid` (UUID, points to `workflow_instances.uuid`)
    *   `step_definition_uuid` (UUID, points to `workflow_steps.uuid`)
    *   `status` (Text)
    *   `started_at`, `finished_at`
    *   `output_id` (UUID, Indexed, Nullable)
    *   `output` (JSON, stores a `StepOutputData` object)
    *   `details` (JSON, for `messages`, `error_message`, `input_data`, etc.)

### 8.2. Database Technology Choice

The chosen database for this project is **MySQL**.

The high-level approach is to provide a suite of `async` functions, one for each CRUD operation on each of the core Pydantic models. This ensures a clean separation of concerns and makes the client logic easier to read and maintain.

Key responsibilities of this layer will include:

-   **Model-Specific Functions**: Implementing functions like `_create_workflow_in_db`, `_get_workflow_from_db`, `_list_workflows_from_db`, `_update_workflow_in_db`, and `_delete_workflow_in_db` for the `WorkflowModel`. Similar sets of functions will be created for `TriggerModel`, `WorkflowStep`, and all the various instance models.
-   **Unified Step Table**: To support the `get_with_details` function efficiently, all step definitions (`CustomLLM`, `CustomAgent`, `StopWorkflowChecker`) should be stored in a single database table. A `type` column (e.g., 'custom_llm') will be used as a discriminator to determine which Pydantic model to instantiate. This avoids multiple lookups to resolve a step's type based on its UUID.
-   **Data Transformation**: Handling the serialization of Pydantic models into the database schema and deserialization back into Pydantic models.
-   **Transaction Management**: Ensuring that complex operations, like creating a workflow and its associated trigger, are handled atomically where necessary.
-   **Error Handling**: Managing database-specific exceptions and propagating them appropriately. 
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

Data flows sequentially through the workflow, where data containers act as "state variables" for the run. The output of any step is available to all subsequent steps. If multiple steps produce the same *type* of data (e.g., refining a summary), later steps will always see the most recently produced version. This allows workflows to progressively refine data.

To use the output of a previous step or the initial trigger data, a placeholder referencing the data's stable **Definition UUID** is used in the `system_prompt`. The syntax is `<<data.{data_container_definition_uuid}>>`.

**Example:**
-   Step 1 produces an "Email Summary", which corresponds to `DataContainerModel` with UUID `4e5b...d1e3f`.
-   Step 2's prompt would be: `"Label this summary: <<data.4e5b8e4e-0b4d-4b8a-9a4e-9f3a2c5d1e3f>>"`

This UUID referencing is handled by the UI. The user simply selects a previous step's output from a dropdown, and the UI inserts the correct placeholder. The workflow engine is then responsible for replacing this placeholder with the actual content of the data instance at runtime.

## 4. Pydantic Models

Below are the proposed Pydantic models for the new workflow structure.

### 4.1. Workflow and Step Definitions

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Union, Optional
from uuid import UUID, uuid4
from datetime import datetime

class StopWorkflowCondition(BaseModel):
    """Defines a rule to evaluate against a data container's output."""
    datacontainer_definition_uuid: UUID # The data container to inspect
    extraction_json_path: str # JSONPath to extract value from raw_data
    operator: Literal["equals", "not_equals", "contains", "greater_than", "less_than"]
    target_value: Any

class DataContainerModel(BaseModel):
    """The definition/schema for a piece of data."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A short, unique name for this data type, e.g., 'email_summary'.")

class CustomLLM(BaseModel):
    """A workflow step definition that calls an LLM without tools."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A unique, user-defined name for this step.")
    description: str = Field(default="", description="A description of what this step does.")
    type: Literal["custom_llm"] = "custom_llm"
    model: str
    system_prompt: str
    output_datacontainer_uuid: UUID = Field(..., description="The UUID of the DataContainer that defines the output of this step.")
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
    output_datacontainer_uuid: UUID = Field(..., description="The UUID of the DataContainer that defines the output of this step.")
    generated_summary: Optional[str] = None # For UI display, auto-generated

class StopWorkflowChecker(BaseModel):
    """A step that checks conditions to stop the workflow based on data from previous steps."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A unique, user-defined name for this step.")
    description: str = Field(default="", description="A description of what this step does.")
    type: Literal["stop_checker"] = "stop_checker"
    stop_conditions: List[StopWorkflowCondition] = Field(...)
    # This step does not produce a DataContainer for other steps to consume.

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
    output_datacontainer_uuid: UUID = Field(..., description="The UUID of the DataContainer that defines the initial output of this trigger.")
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

class DataContainerInstanceModel(BaseModel):
    """An instance of data produced by a workflow step run."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_instance_uuid: UUID # Direct link to the run for easy lookup.
    datacontainer_uuid: UUID # Link back to the definition/type of data.
    step_instance_uuid: Optional[UUID] = None # The step that produced this data. Null for initial trigger data.
    raw_data: Any
    generated_summary: Optional[str] = None # LLM-generated summary of the markdown data if markdown data, otherwise of the raw_data
    markdown_representation: Optional[str] = None # For UI display

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
    output_container_instance_uuid: Optional[UUID] = None # Link to the DataContainerInstanceModel
    
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
    output_container_instance_uuid: Optional[UUID] = None # Link to the DataContainerInstanceModel

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
    # This step does not produce an output container

WorkflowStepInstance = Union[CustomLLMInstanceModel, CustomAgentInstanceModel, StopWorkflowCheckerInstanceModel]

class WorkflowInstanceModel(BaseModel):
    """An instance of an executed workflow."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    workflow_definition_uuid: UUID
    status: Literal["running", "completed", "stopped", "failed"]
    triggering_data: Any # The initial data that started the workflow
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
├── datacontainer_client.py # Handles DataContainerModel logic
├── models.py               # Contains all the Pydantic models
└── internals/
    ├── __init__.py
    ├── database.py         # Handles direct database interactions for all workflow models.
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
    *   `async def list_instances(workflow_uuid: UUID) -> List[WorkflowInstanceModel]:` Lists all runs for a given workflow.
    *   `async def cancel_instance(instance_uuid: UUID) -> None:` Cancels a running workflow.
*   **Utility Functions**
    *   `async def list_available_trigger_types() -> List[Dict[str, Any]]:` Returns a list of all available trigger types that can be added to a workflow. This is a pass-through from the `trigger_client`.
    *   `async def discover_mcp_tools() -> List[Dict[str, Any]]:` Discovers all available tools from all connected MCP servers. This is a pass-through from the `agent_client`.

#### `workflow/llm_client.py` (Standalone Manager for `CustomLLM` Steps)

*   **Definition Management**
    *   `async def create(name: str, model: str, system_prompt: str) -> CustomLLM:` Creates a new, standalone `CustomLLM` step definition. Internally, this will first create an associated `DataContainerModel` to define this step's output and assign its UUID to the `output_datacontainer_uuid` field. This is primarily called by the `workflow_client` facade.
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
    *   `async def create(name: str, model: str, system_prompt: str) -> CustomAgent:` Creates a new, standalone `CustomAgent` step definition. Internally, this will first create an associated `DataContainerModel` to define this step's output and assign its UUID to the `output_datacontainer_uuid` field. This is primarily called by the `workflow_client` facade.
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
*   `async def create(workflow_uuid: UUID, trigger_type_id: str) -> TriggerModel:` Creates a new trigger instance with default settings for the given type. Internally, this first creates an associated `DataContainerModel` to define the trigger's initial output and assigns its UUID to the `output_datacontainer_uuid` field. This is primarily called by the `workflow_client` facade.
*   `async def get(uuid: UUID) -> Optional[TriggerModel]:` Retrieves a trigger definition.
*   `async def get_for_workflow(workflow_uuid: UUID) -> Optional[TriggerModel]:` Retrieves the trigger for a specific workflow.
*   `async def list() -> List[TriggerModel]:` Lists all triggers.
*   `async def save(trigger_model: TriggerModel) -> TriggerModel:` Updates the state of a trigger.
*   `async def delete(uuid: UUID) -> None:` Deletes a trigger.

#### `workflow/datacontainer_client.py` (Handles `DataContainerModel`)

*   `async def create() -> DataContainerModel:` Creates a new, anonymous `DataContainerModel` definition. This is called implicitly by other clients (e.g., `llm_client`) when creating a new step or trigger.
*   `async def create_instance(workflow_instance_uuid: UUID, datacontainer_uuid: UUID, raw_data: Any, step_instance_uuid: Optional[UUID] = None, markdown_representation: Optional[str] = None) -> DataContainerInstanceModel:` Creates a new data instance. This function is responsible for synchronously generating a summary (from markdown if available, otherwise raw_data) before saving the complete instance to the database.
*   `async def get(uuid: UUID) -> Optional[DataContainerModel]:` Retrieves a `DataContainerModel` definition.
*   `async def list() -> List[DataContainerModel]:` Lists all `DataContainerModel` definitions.
*   `async def resolve_data_from_run(workflow_instance_uuid: UUID, datacontainer_definition_uuid: UUID, target_format: Literal['compressed', 'uncompressed']) -> Any:` Looks up the correct data instance for a given workflow run and data definition. It then returns the data in the specified format:
    - `compressed`: A small JSON object with the instance UUID and summary, for use by `CustomAgent` steps.
    - `uncompressed`: The full data content (markdown if available, else raw_data), for use by `CustomLLM` steps.

## 6. Execution Flow

1.  A trigger receives an event (e.g., a new email arrives).
2.  The trigger's `filter_rules` are applied to the event data.
3.  If the rules match, the trigger system calls `workflow_client.create_instance`, passing the `workflow_uuid` and the event data.
4.  The workflow engine creates a `WorkflowInstanceModel` record with status `running`. The trigger's output is saved by calling `datacontainer_client.create_instance`, which synchronously generates a summary and saves the complete `DataContainerInstanceModel`.
5.  The engine iterates through the `steps` (definitions) of the `WorkflowModel` in order.
6.  For each step definition:
    a. A corresponding Step Instance Model (`CustomLLMInstanceModel`, etc.) is created with status `running`.
    b. The `system_prompt` for the step is scanned for `<<data.{uuid}>>` placeholders.
    c. For each placeholder, the engine determines the correct format and calls `datacontainer_client.resolve_data_from_run`.
        - If the step is a `CustomAgent`, it calls with `target_format='compressed'`.
        - If the step is a `CustomLLM`, it calls with `target_format='uncompressed'`.
    d. The function returns the correctly formatted data (a small JSON reference for agents, full content for LLMs), which is then injected into the prompt.
    e. The step is executed (e.g., an LLM or Agent call is made).
    f. If the step is a `StopWorkflowChecker`, its logic is evaluated. If a stop condition is met, the `WorkflowInstanceModel` status is set to `stopped`, and execution halts.
    g. If the step is not a `StopWorkflowChecker`, its output is saved via `datacontainer_client.create_instance`. This creates a new `DataContainerInstanceModel`, overwriting the "current value" for that data type for any subsequent steps.
    h. The step instance's status is updated to `completed` (or `failed`).
7.  Once all steps are completed, the `WorkflowInstanceModel` status is set to `completed`.

## 7. Backend Responsibilities

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
    *   `steps` (JSON array of `workflow_steps.uuid`s, maintains order)
    *   `created_at`, `updated_at`

*   **`workflow_steps`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `name` (Text)
    *   `type` (Text Discriminator: "custom_llm", "custom_agent", "stop_checker")
    *   `details` (JSON blob for type-specific settings like `model`, `system_prompt`, `tools`, `stop_conditions`, etc.)
    *   `created_at`, `updated_at`

*   **`data_containers`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `name` (Text, should be unique per user)

*   **`triggers`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `workflow_uuid` (UUID)
    *   `details` (JSON blob for `filter_rules`, `initial_data_description`, etc.)
    *   `created_at`, `updated_at`

*   **`workflow_instances`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `workflow_definition_uuid` (UUID, points to `workflows.uuid`)
    *   `status` (Text: "running", "completed", etc.)
    *   `triggering_data` (JSON)
    *   `created_at`, `updated_at`

*   **`workflow_step_instances`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `workflow_instance_uuid` (UUID, points to `workflow_instances.uuid`)
    *   `step_definition_uuid` (UUID, points to `workflow_steps.uuid`)
    *   `status` (Text)
    *   `started_at`, `finished_at`
    *   `details` (JSON blob for `messages`, `error_message`, `input_data`, etc.)
    *   `output_container_instance_uuid` (UUID, nullable)

*   **`data_container_instances`**
    *   `uuid` (Primary Key)
    *   `user_id` (UUID, owner identifier)
    *   `workflow_instance_uuid` (UUID, points to `workflow_instances.uuid`)
    *   `datacontainer_uuid` (UUID, points to `data_containers.uuid`)
    *   `step_instance_uuid` (UUID, nullable, points to `workflow_step_instances.uuid`)
    *   `raw_data` (JSON or Text)
    *   `markdown_representation` (Text, for UI)

The high-level approach is to provide a suite of `async` functions, one for each CRUD operation on each of the core Pydantic models. This ensures a clean separation of concerns and makes the client logic easier to read and maintain.

Key responsibilities of this layer will include:

-   **Model-Specific Functions**: Implementing functions like `_create_workflow_in_db`, `_get_workflow_from_db`, `_list_workflows_from_db`, `_update_workflow_in_db`, and `_delete_workflow_in_db` for the `WorkflowModel`. Similar sets of functions will be created for `TriggerModel`, `DataContainerModel`, and all the various step definition and instance models.
-   **Unified Step Table**: To support the `get_with_details` function efficiently, all step definitions (`CustomLLM`, `CustomAgent`, `StopWorkflowChecker`) should be stored in a single database table. A `type` column (e.g., 'custom_llm') will be used as a discriminator to determine which Pydantic model to instantiate. This avoids multiple lookups to resolve a step's type based on its UUID.
-   **Data Transformation**: Handling the serialization of Pydantic models into the database schema and deserialization back into Pydantic models.
-   **Transaction Management**: Ensuring that complex operations, like creating a workflow and its associated trigger, are handled atomically where necessary.
-   **Error Handling**: Managing database-specific exceptions and propagating them appropriately. 
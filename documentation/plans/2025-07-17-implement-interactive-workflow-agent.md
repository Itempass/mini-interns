# Plan: Implement Interactive Workflow Agent

**Date:** 2025-07-17
**Status:** Proposed

## 1. Summary

The goal of this project is to implement a chat-based agent in the "Workflow Settings" UI. This agent will assist users in creating, modifying, and managing their workflows through a conversational interface. It will have access to a set of tools to perform actions like adding steps, configuring triggers, and updating settings on behalf of the user.

## 2. Architecture Overview

The `workflow_agent` will be a self-contained module composed of two distinct components:

1.  **`client`**: The agent's "brain" and public-facing interface. It contains the core agent logic and is what the main API will interact with.
2.  **`mcp`**: The agent's "hands." This is a lightweight MCP server that exposes workflow modification functions as tools for the agent to consume.

This separation ensures that the agent's logic is decoupled from the tool implementation, providing modularity and clarity.

### Final File Structure

```
workflow_agent/
├── __init__.py
├── client/
│   ├── __init__.py
│   ├── client.py
│   ├── models.py
│   ├── system_prompt.md
│   └── internals/
│       ├── __init__.py
│       └── agent_runner.py
│
└── mcp/
    ├── __init__.py
    ├── main.py
    ├── mcp_builder.py
    └── tools.py
```

## 3. Phase 1: Build the `mcp` Tool Server

This phase focuses on creating the backend server that provides the tools for the agent.

### 3.1. `mcp/tools.py`

Implement tool functions that wrap `workflow.client` and other clients (`trigger_client`, `agent_client`, etc.). The function signature and docstring are critical, as the docstring is what the agent will see. The tools should return JSON-serializable dictionaries (by calling `.model_dump()`) instead of Pydantic models.

**Tool Signatures:**

*   `get_workflow_details(workflow_uuid: str, user_id: str) -> dict`
    *   **Docstring**: "Retrieves the full, detailed configuration of a specific workflow, including its name, description, trigger, and all of its steps in order. Returns a `WorkflowWithDetails` model."
    *   **Implementation**: Wraps `workflow.client.get_with_details`.

*   `list_available_triggers() -> List[dict]`
    *   **Docstring**: "Returns a list of all available trigger types that can be used to start a workflow. Each trigger type includes its 'id', 'name', and 'description'."
    *   **Implementation**: Wraps `workflow.client.list_available_trigger_types`.

*   `set_trigger(workflow_uuid: str, trigger_type_id: str, user_id: str) -> dict`
    *   **Docstring**: "Sets or replaces the trigger for a specific workflow. Use 'list_available_triggers' to find the correct 'trigger_type_id'. Returns the updated `WorkflowModel`."
    *   **Implementation**: Wraps `workflow.client.set_trigger`.

*   `update_trigger_settings(trigger_uuid: str, filter_rules: dict, user_id: str) -> dict`
    *   **Docstring**: "Updates the settings of an existing trigger. The 'filter_rules' determine the conditions under which the workflow runs. The 'trigger_uuid' can be found in the workflow details. Returns the updated `TriggerModel`."
    *   **Implementation**: This will require a new function in `trigger_client.py` to update a trigger by UUID and settings, as the main `workflow.py` endpoint only updates it based on a full request body.

*   `list_available_step_types() -> List[dict]`
    *   **Docstring**: "Returns a list of all available step types that can be added to a workflow, such as 'custom_llm' or 'custom_agent'."
    *   **Implementation**: Wraps `workflow.client.list_available_step_types`.

*   `add_step(workflow_uuid: str, step_type: str, name: str, user_id: str) -> dict`
    *   **Docstring**: "Adds a new step to the end of a specified workflow. Use 'list_available_step_types' to see valid options for 'step_type'. Returns the updated `WorkflowModel`."
    *   **Implementation**: Wraps `workflow.client.add_new_step`.

*   `remove_step(workflow_uuid: str, step_uuid: str, user_id: str) -> None`
    *   **Docstring**: "Removes a specific step from a workflow. The agent can find the 'step_uuid' from the workflow details."
    *   **Implementation**: Wraps `workflow.client.delete_step`.

*   `reorder_steps(workflow_uuid: str, ordered_step_uuids: List[str], user_id: str) -> dict`
    *   **Docstring**: "Changes the execution order of steps in a workflow. Provide the full list of 'step_uuid's in the desired new order. Returns the updated `WorkflowModel`."
    *   **Implementation**: Wraps `workflow.client.reorder_steps`.

*   `update_system_prompt_for_step(workflow_uuid: str, step_uuid: str, system_prompt: str, user_id: str) -> dict`
    *   **Docstring**: "Updates the system prompt for a specific workflow step. This works for steps of type 'custom_llm' or 'custom_agent'. Returns the updated step model."
    *   **Implementation**: This tool will act as an abstraction layer. It will internally call `workflow.client.get_with_details` to find the specific step object, modify its `system_prompt` field, and then call `workflow.client.update_step` with the modified object.

*   `list_available_mcp_tools() -> List[dict]`
    *   **Docstring**: "Returns a list of all available tools from all connected MCP servers that can be enabled for an agent step."
    *   **Implementation**: Wraps `workflow.client.discover_mcp_tools`.

*   `update_step_mcp_tools(workflow_uuid: str, step_uuid: str, enabled_tools: List[str], user_id: str) -> dict`
    *   **Docstring**: "Updates the set of enabled tools for a specific agent step. This only works for steps of type 'custom_agent'. Provide the full list of tool names that should be enabled. Returns the updated step model."
    *   **Implementation**: This tool will also perform a "read-modify-write" cycle using only the public client. It will call `workflow.client.get_with_details` to find the step, update its `tools` dictionary, and then call `workflow.client.update_step`.

### 3.2. `mcp/main.py` & `mcp/mcp_builder.py`

Create a standard FastAPI MCP server that registers and exposes the functions from `tools.py`. This server will run as a separate process managed by `supervisord`.

**Reference Implementation:** The implementation should closely follow the pattern established by `mcp_servers/tone_of_voice_mcpserver/`. This includes the structure of `main.py` for creating the FastAPI app and `mcp_builder.py` for defining the service and registering tools.

## 4. Phase 2: Build the `client` Agent Logic

This phase focuses on creating the agent's "brain" and its client interface.

### 4.1. `client/models.py`

Define the data structures for API communication.

**`ChatMessage` Model:**
```json
{
  "role": "user | assistant | tool",
  "content": "string",
  "tool_calls": "Optional[List[...]]",
  "tool_call_id": "Optional[string]"
}
```

**`ChatRequest` Model:**
```json
{
  "conversation_id": "string",
  "messages": "List[ChatMessage]"
}
```

**`ChatStepResponse` Model:**
```json
{
  "conversation_id": "string",
  "messages": "List[ChatMessage]",
  "is_complete": "bool"
}
```

### 4.2. `client/system_prompt.md`

Create a detailed system prompt that instructs the LLM on its role as a helpful workflow assistant. The prompt will include descriptions of the available tools from the `mcp` server and examples of how to use them.

### 4.3. `client/internals/agent_runner.py`

Implement the core agent logic in a `run_agent_turn` function. This runner will:
1.  Instantiate a `fastmcp.Client` to communicate with the `mcp` server.
2.  Manage the conversation history.
3.  Call the LLM with the prompt, history, and tools.
4.  Use its MCP client to execute any tool calls requested by the LLM.
5.  Return the final response.

**Reference Implementation:** For an example of how to instantiate and use an MCP client to call tools from within a runner, see `workflow/internals/agent_runner.py`. Our new runner will be simpler and dedicated, but the pattern of discovering MCP clients and calling tools will be similar.

### 4.4. `client/client.py`

Create a high-level `chat_with_workflow_agent` function. This will be the clean, public entry point that the API endpoint calls. It will handle orchestrating calls to the `agent_runner`.

## 5. Phase 3: Integration

This phase connects the new `workflow_agent` to the existing application.

### 5.1. API Endpoint

**File:** `api/endpoints/workflow.py`
**Action:** Add a new endpoint that executes a single step of the agent's turn.

*   **Endpoint:** `POST /workflows/{workflow_uuid}/chat/step`
*   **Request Body:** `ChatRequest` (from `workflow_agent.client.models`)
*   **Response Body:** `ChatStepResponse` (from `workflow_agent.client.models`)
*   **Implementation:** The endpoint will call a function like `workflow_agent.client.client.run_chat_step`. This function will inspect the *last* message in the history to decide the next action:
  - If the last message is from the `user`, it calls the LLM.
  - If the last message is from the `assistant` with a `tool_calls` request, it executes the requested tool.
It then appends the result (either the assistant's new message or the tool's output) to the history. The `is_complete` flag in the response is set to `true` **only if** the newly added message is from the assistant and does **not** contain a tool call. Otherwise, it is `false`.

### 5.2. Deployment

**File:** `supervisord.conf`
**Action:** Add a new `[program:workflow_agent_mcp]` section to run the `workflow_agent.mcp.main` server as a persistent process.

### 5.3. Frontend

**File:** `frontend/components/WorkflowChat.tsx` (New)
**Action:**
1.  Create a new chat component to be displayed in the `WorkflowSettings.tsx` view.
2.  The component will manage a list of chat messages.
3.  On send, it will call the `POST /workflows/{workflow_uuid}/chat` endpoint.
4.  If the response `workflow_updated` is `true`, it will call the `onWorkflowUpdate` callback to refresh the parent `WorkflowSettings` view.

### 5.4. Conversation State Management

The conversation state will be managed by the frontend, which will act as the conductor for the agent's multi-step thinking process.

1.  **State Holder**: The `WorkflowChat.tsx` React component will hold the `messages` array in its local state. This is the single source of truth for the UI.
2.  **Request Flow**: When the user initiates a turn, the frontend calls the `POST /.../chat/step` endpoint with the entire conversation history.
3.  **Response Flow**: The backend performs a single action (one LLM call or one tool execution), appends the result to the history, and returns the complete, updated history along with an `is_complete` flag.
4.  **UI Update & Loop**: The frontend replaces its local state with the history from the response, causing the UI to re-render. This shows the agent's "thought" process in near real-time. If `is_complete` is `false` (e.g., after the agent decides to use a tool), the frontend immediately calls the endpoint again with the new history. This continues the loop until the agent's turn is finished and it returns a final text response.
5.  **Future-Proofing**: The `WorkflowChat.tsx` component will generate a unique `conversation_id` (UUID) when it first mounts. This ID will be included in every `ChatRequest`. The backend will receive but not act on this ID in the initial implementation. 
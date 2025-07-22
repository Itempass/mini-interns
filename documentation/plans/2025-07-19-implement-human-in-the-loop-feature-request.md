# Plan: Implement Human-in-the-Loop for Feature Requests

**Date**: 2025-07-19
**Author**: Gemini

## 1. Objective

To implement a "human-in-the-loop" capability for the Workflow Agent. This will allow the agent to request user input for tasks it cannot complete on its own, starting with a "Feature Request" tool. When the agent determines a feature is missing, it will pause and prompt the user for details via a dedicated UI form. After submission, the agent will resume its operation with the user's input as context.

This plan follows **Option 3** from our previous discussion, which involves creating a dedicated API flow for handling human input, ensuring a robust and scalable solution.

## 2. High-Level Plan

1.  **Backend**: Extend the API contract to support a "human input required" state.
2.  **Backend**: Implement a new `feature_request` tool that triggers this state.
3.  **Backend**: Create a new endpoint to receive the user's input and resume the agent's execution.
4.  **Frontend**: Update the chat component to render a form when the API signals that human input is required.
5.  **Frontend**: Implement the service call to submit the form data to the new endpoint.

## 3. Detailed Implementation Steps

### Step 3.1: Backend API & Model Changes

This section details the backend work, which follows a `PAUSE -> RESUME` pattern. First, the agent's tool call is paused to get user input. Then, a separate endpoint resumes the flow once the input is provided.

#### 3.1.1. Modify `ChatStepResponse` Model (No Change)

This model in `workflow_agent/client/models.py` is still correct. The `human_input_required` field will signal the PAUSE.

```python
# In workflow_agent/client/models.py

class HumanInputRequired(BaseModel):
    type: str  # 'feature_request'
    tool_call_id: str
    data: Dict[str, Any] # Context for the form, e.g., {"name": "Suggested feature"}

class ChatStepResponse(BaseModel):
    conversation_id: str
    messages: List[ChatMessage]
    is_complete: bool
    human_input_required: Optional[HumanInputRequired] = None
```

#### 3.1.2. Define the User-Facing "Trigger" Tool [COMPLETED]

In `workflow_agent/mcp/tools.py`, the tool the LLM calls is a "trigger." Its sole purpose is to gather suggestions from the LLM. The docstring is critical to guide the LLM to provide complete suggestions for both arguments.

```python
# In workflow_agent/mcp/tools.py

@tool
def feature_request(suggested_name: str, suggested_description: str):
    """
    Proposes a feature request to the user for confirmation. Call this when you have a clear
    idea for a new feature. The system will show a form to the user pre-filled with the
    suggested_name and suggested_description you provide. The user can then edit them
    before final submission. Returns a confirmation message upon submission.
    """
    # This function is a placeholder. The backend orchestrates the human-in-the-loop
    # flow when this tool is called. The real logic happens after user input.
    pass
```

The internal logic, which will be executed in the RESUME step, is now simplified to log the captured data and return a confirmation. This logic will be inside the `feature_request` tool itself, which will be called by the RESUME endpoint.

```python
# The updated logic inside the final feature_request tool in workflow_agent/mcp/tools.py

logger.info(f"--- Feature Request Captured ---\nName: {name}\nDescription: {description}\n---------------------------------")
    
confirmation_message = (
    f"Feature request '{name}' with description '{description}' has been successfully captured. "
    "Acknowledge this and ask how else you can help."
)
return confirmation_message
```


#### 3.1.3. **PAUSE**: Update Agent Runner to Pass Suggestions to Frontend

The PAUSE logic now extracts the LLM's complete suggestion and forwards it to the frontend to pre-fill the form.

-   **File to modify**: `workflow_agent/client/internals/agent_runner.py`
-   **Logic**:
    -   Intercept the tool call to `feature_request`.
    -   Extract the `suggested_name` and `suggested_description` from the tool call's arguments.
    -   Create the `HumanInputRequired` object. Its `data` field will contain `{ "name": suggested_name, "description": suggested_description }`.
    -   Return the `ChatStepResponse` to pause the flow and trigger the pre-filled form on the frontend.

#### 3.1.4. **RESUME**: Update Endpoint to Execute Logic with Final User Data

The RESUME logic takes the user's final, edited data and uses it to execute the simplified tool logic.

-   **File to modify**: `api/endpoints/workflow.py`
-   **Endpoint Logic**:
    1.  Receive the `HumanInputSubmission` from the frontend. The `user_input` field now contains the final, user-edited `name` and `description`.
    2.  **Execute the real logic**: Find and call the `feature_request` tool with the final, user-edited `name` and `description`.
    3.  The return value of the tool (the confirmation message) becomes our `tool_result`.
    4.  Create a `tool` result message, linking it with the `tool_call_id` of the original `feature_request` call.
    5.  Append this result to the message history and call `run_chat_step` to let the agent continue.

### Step 3.2: Frontend Changes

#### 3.2.1. Update API Service Layer

In `frontend/services/workflows_api.ts`, we need to:
1.  Update the `ChatStepResponse` type to include the new `human_input_required` field.
2.  Create a new function, `submitHumanInput`, to call our new backend endpoint.

#### 3.2.2. Update the `WorkflowChat` Component

This is the most significant frontend change.

-   **File to modify**: `frontend/components/WorkflowChat.tsx`
-   **New File**: `frontend/components/chat_input/FeatureRequestForm.tsx`
-   **Logic**:
    1.  In `WorkflowChat.tsx`, the `runConversation` function will check for `response.human_input_required`. If found, it will stop its loop and store the request data in a new state variable: `const [humanInputRequest, setHumanInputRequest] = useState(null);`.
    2.  The main render function of `WorkflowChat.tsx` will be updated:
        ```jsx
        {humanInputRequest ? (
          <FeatureRequestForm
            request={humanInputRequest}
            onSubmit={handleFeatureRequestSubmit}
          />
        ) : (
          // Original chat input textarea and send button
        )}
        ```
    3.  The new `FeatureRequestForm.tsx` component will render the form and receive the `onSubmit` handler as a prop.
    4.  A new handler, `handleFeatureRequestSubmit`, will be created in `WorkflowChat.tsx`:
        -   It will be an `async` function that takes the user's form data as an argument.
        -   It will set a loading state (e.g., `isAgentThinking(true)`).
        -   It will call the new `submitHumanInput` service function, passing the **current messages from state**, the `tool_call_id`, and the form data.
        -   When the API call returns, it will clear the `humanInputRequest` state (`setHumanInputRequest(null)`).
        -   Crucially, it will then **re-start the `runConversation` loop**, passing it the new list of messages returned from the `submitHumanInput` call. This handles the handoff back to the main logic flow.

### Step 3.3: Error Handling and Edge Cases

A robust implementation must account for failures.

-   **API Error on Submission**: The `handleFeatureRequestSubmit` function in `WorkflowChat.tsx` should have a `try...catch` block. If the `submitHumanInput` call fails, it should display an error message to the user (e.g., using a toast notification) and leave the form visible for a retry. The loading state should be disabled.
-   **UI State Management**: While the `FeatureRequestForm` is active (`humanInputRequest` is not null), the main chat input `textarea` must be explicitly disabled to prevent conflicting user actions.
-   **User Abandonment**: For this initial implementation, we will not persist the "human input required" state. If the user reloads the page, the conversation will reset to its last saved state, and the request for input will be lost. This is an acceptable trade-off for v1.


## 4. Summary of Changes by File

-   `workflow_agent/client/models.py`: Add `human_input_required` to `ChatStepResponse`.
-   `workflow_agent/mcp/tools.py`: Add new `feature_request` tool definition.
-   `workflow_agent/client/internals/agent_runner.py`: Add logic to intercept the `feature_request` tool call.
-   `api/endpoints/workflow.py`: Add `POST .../submit_human_input` endpoint and associated logic.
-   `frontend/services/workflows_api.ts`: Add `submitHumanInput` function and update types.
-   `frontend/components/WorkflowChat.tsx`: Add state and logic to conditionally render the human input form.
-   `frontend/components/chat_input/FeatureRequestForm.tsx`: **(New File)** Component containing the form for the user to submit a feature request.

This plan provides a clear path to implementing the feature with a clean separation of concerns, ensuring the system remains robust and extensible for future human-in-the-loop interactions. 
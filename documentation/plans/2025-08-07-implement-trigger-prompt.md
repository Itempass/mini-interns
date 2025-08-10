### Plan: Implement Trigger Prompt

#### 1. Frontend Changes (`/frontend`)

*   **`frontend/components/workflow/editors/EditNewEmailTrigger.tsx`**:
    *   Add a new `textarea` for the "Trigger Prompt".
    *   Add a `<select>` dropdown for model selection, similar to the one in `EditCustomLLMStep.tsx`.
    *   Fetch available LLM models using `getAvailableLLMModels` from `workflows_api.ts`.
    *   Add state management for the trigger prompt and the selected model.
    *   Update the `onSave` handler to include `trigger_prompt` and `trigger_model` in the payload sent to the backend.

*   **`frontend/services/workflows_api.ts`**:
    *   Update the `TriggerModel` interface to include `trigger_prompt?: string` and `trigger_model?: string`.
    *   Ensure the `updateWorkflowTrigger` function can send `trigger_prompt` and `trigger_model` to the backend.

#### 2. Backend API Changes (`/api`)

*   **`/api/types/api_models/workflow.py`**:
    *   Update the `UpdateTriggerRequest` pydantic model to include `trigger_prompt: Optional[str] = None` and `trigger_model: Optional[str] = None`.
*   **`/api/endpoints/workflow.py`**:
    *   In `update_workflow_trigger`, update the trigger's `details` dictionary with the `trigger_prompt` and `trigger_model` from the request.

#### 3. Workflow Model Changes (`/workflow`)

*   **`/workflow/models.py`**:
    *   Update the `TriggerModel` Pydantic model to include `trigger_prompt: Optional[str] = None` and `trigger_model: Optional[str] = None`. These fields will be populated from the `details` JSON blob from the database.

#### 4. Trigger Logic Changes (`/triggers`)

*   **`/triggers/main.py`**:
    *   In `process_message`, after the `passes_filter` check, check if `trigger.trigger_prompt` and `trigger.trigger_model` have values.
    *   If they do, call the selected LLM with a system prompt that includes the user's `trigger_prompt` and the email content.
    *   The prompt to the LLM should ask for a JSON object with a boolean flag, like `{"continue_processing": true/false}`.
    *   Based on the LLM's response, the trigger will either continue or stop. 
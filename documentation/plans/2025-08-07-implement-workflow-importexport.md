# 2025-08-07: Workflow Import/Export Plan

## 1. Overview

This document outlines the plan to implement a workflow import and export feature. This will allow users to save a workflow's configuration as a JSON file and later re-import it, streamlining the process of sharing and backing up workflows.

## 2. Feature Breakdown

### 2.1. Backend

- **Create a new API endpoint for exporting workflows.**
  - **File:** `api/endpoints/workflow.py`
  - **Endpoint:** `GET /api/workflows/{workflow_uuid}/export`
  - This endpoint will retrieve the complete workflow data using the existing `workflow_client.get_with_details` function.
  - The response will be a JSON file, with a `Content-Disposition` header to prompt a download.

- **Create a new API endpoint for importing workflows.**
  - **File:** `api/endpoints/workflow.py`
  - **Endpoint:** `POST /api/workflows/import`
  - This endpoint will accept a JSON file containing the workflow data.
  - It will parse the file and create a new workflow, including all its steps and triggers, using a new `workflow_client.import_workflow` function.

- **Implement the `import_workflow` function.**
  - **File:** `workflow/client.py`
  - **Function:** `import_workflow(workflow_data: dict, user_id: UUID)`
  - This function will be responsible for creating a new workflow from the imported data, ensuring all steps and triggers are correctly recreated and linked.

### 2.2. Frontend

- **Add an "Export" button to the workflow settings.**
  - **File:** `frontend/components/WorkflowSettings.tsx`
  - An "Export" button will be added next to the "Delete Workflow" button.
  - Clicking this button will trigger the export process.

- **Add an "Import" button to the workflow sidebar.**
  - **File:** `frontend/components/WorkflowSidebar.tsx`
  - An "Import" button will be added to the sidebar.
  - Clicking this button will open a file selection dialog to choose the workflow JSON file to import.

- **Implement the `exportWorkflow` API call.**
  - **File:** `frontend/services/workflows_api.ts`
  - **Function:** `exportWorkflow(workflowId: string)`
  - This function will make a `GET` request to the new `/api/workflows/{workflow_uuid}/export` endpoint and handle the file download.

- **Implement the `importWorkflow` API call.**
  - **File:** `frontend/services/workflows_api.ts`
  - **Function:** `importWorkflow(file: File)`
  - This function will read the selected JSON file and send its content to the `/api/workflows/import` endpoint.

## 3. Data Format

The exported JSON file will have the same structure as the `WorkflowWithDetails` model:

```json
{
  "uuid": "string",
  "user_id": "string",
  "name": "string",
  "description": "string",
  "is_active": "boolean",
  "trigger": {
    "uuid": "string",
    "user_id": "string",
    "workflow_uuid": "string",
    "filter_rules": {},
    "initial_data_description": "string",
    "created_at": "string",
    "updated_at": "string"
  },
  "steps": [
    {
      "uuid": "string",
      "user_id": "string",
      "name": "string",
      "description": "string",
      "type": "string",
      "model": "string",
      "system_prompt": "string"
    }
  ],
  "template_id": "string",
  "template_version": "string",
  "created_at": "string",
  "updated_at": "string"
}
```

## 4. Implementation Steps

1.  **Backend Development:**
    1.  Implement the `GET /api/workflows/{workflow_uuid}/export` endpoint in `api/endpoints/workflow.py`.
    2.  Implement the `POST /api/workflows/import` endpoint in `api/endpoints/workflow.py`.
    3.  Implement the `import_workflow` function in `workflow/client.py`.

2.  **Frontend Development:**
    1.  Add the "Export" button in `frontend/components/WorkflowSettings.tsx`.
    2.  Add the "Import" button in `frontend/components/WorkflowSidebar.tsx`.
    3.  Implement `exportWorkflow` in `frontend/services/workflows_api.ts`.
    4.  Implement `importWorkflow` in `frontend/services/workflows_api.ts`.
    5.  Connect the new buttons to their respective API functions.

This plan ensures a clear and structured approach to implementing the workflow import/export feature, with a clean separation of concerns between the frontend and backend. 
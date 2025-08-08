# Plan: Implement RAG Workflow Step (Phased Approach)

**Date:** 2025-08-08

**Author:** AI Assistant

## Phase 1: Vector Database Management

This phase focuses exclusively on creating the backend and a dedicated frontend page to perform full CRUD (Create, Read, Update, Delete) operations on vector databases. This provides a solid, testable foundation before integrating with the workflow engine.

### 1.1. Backend

**1.1.1. Database Schema**

*   **File to Create:** `rag/schema.sql`
*   **Table:** `vector_databases`
    *   `uuid` (BINARY(16), PK)
    *   `user_id` (BINARY(16), FK)
    *   `name` (VARCHAR(255))
    *   `type` (ENUM('internal', 'external'))
    *   `provider` (VARCHAR(255))
    *   `settings` (JSON)
    *   `status` (VARCHAR(50))
    *   `error_message` (TEXT)
    *   `created_at`, `updated_at` (TIMESTAMP)

**1.1.2. Pydantic Models**

*   **File to Create:** `rag/models.py`
*   **Model:** `VectorDatabase` to represent the table structure.

**1.1.3. RAG Client (Business Logic)**

This client will contain all business logic for interacting with vector databases, abstracting the details from the API layer.

*   **File to Create:** `rag/client.py`
*   **Functions:**
    *   `async def create_vector_database(...)`
    *   `async def get_vector_database(...)`
    *   `async def list_vector_databases(...)`
    *   `async def update_vector_database(...)`
    *   `async def delete_vector_database(...)`

**1.1.4. API Endpoints (Wrapper)**

The API endpoints will be thin wrappers that call the `rag/client.py` functions.

*   **File to Create:** `api/endpoints/rag.py`
*   **Router Prefix:** `/rag`
*   **Endpoints:**
    *   `POST /vector-databases`: Calls `rag.client.create_vector_database`.
    *   `GET /vector-databases`: Calls `rag.client.list_vector_databases`.
    *   `GET /vector-databases/{uuid}`: Calls `rag.client.get_vector_database`.
    *   `PUT /vector-databases/{uuid}`: Calls `rag.client.update_vector_database`.
    *   `DELETE /vector-databases/{uuid}`: Calls `rag.client.delete_vector_database`.

### 1.2. Frontend

**1.2.1. Update Settings UI**

The settings page uses a sidebar for navigation. We will add a new category to it.

*   **File to Edit:** `frontend/components/settings/SettingsSidebar.tsx`
*   **Change:** Add a new "Vector Databases" item to the sidebar. Clicking this item will set the `selectedCategory` state to `'vector-databases'`.

**1.2.2. Create Vector Database Settings Component**

*   **File to Create:** `frontend/components/settings/VectorDatabasesSettings.tsx`
*   **Purpose:** This component will contain all UI for managing vector databases. It will be responsible for:
    *   Fetching and displaying a list of currently configured vector databases.
    *   Providing buttons to trigger "add", "edit", and "delete" actions.
    *   Rendering modals or forms for creating and editing vector database configurations. These forms will be dynamic based on the selected provider.

**1.2.3. Integrate New Component into Settings Page**

*   **File to Edit:** `frontend/app/settings/page.tsx`
*   **Change:** Add a new entry to the conditional rendering block to display the `VectorDatabasesSettings` component when the `selectedCategory` state is `'vector-databases'`.

**1.2.4. API Service**

*   **File to Edit:** `frontend/services/api.ts` (or a new `frontend/services/rag_api.ts`)
*   **Functions:** Add functions to call the new `/rag/vector-databases` endpoints.

**1.2.3. UI Components**

*   Create components for:
    1.  Listing all configured vector databases.
    2.  A modal/form for adding and editing vector databases. This form should dynamically render fields based on the selected `provider` as defined in `rag/available.json`.

## Phase 2: RAG Workflow Step Integration

Once Phase 1 is complete, we will integrate the RAG functionality as a new step type in the workflow engine.

### 2.1. Backend

**2.1.1. Database Schema**

*   **File to Edit:** `workflow/schema.sql`
*   **Change:** Add `'rag'` to the `type` column in the `workflow_steps` table.

**2.1.2. Pydantic Models**

*   **File to Edit:** `workflow/models.py`
*   **Model:** Create `RAGStep` model and add it to the `WorkflowStep` Union.

**2.1.3. Business Logic Integration**

*   **File to Edit:** `rag/client.py`
    *   **New Function:** `async def execute_step(...)`
*   **File to Create:** `rag/internals/runner.py`
    *   **New Function:** `async def run_rag_step(...)` to handle the core logic of vector search and reranking.
*   **File to Edit:** `workflow/internals/runner.py`
    *   Update `run_workflow` to handle the `'rag'` step type by calling `rag.client.execute_step`.
    *   Update `_prepare_input` to resolve placeholders in the `RAGStep`'s `prompt` field.

### 2.2. Frontend

**2.2.1. UI Components**

*   **File to Create:** `frontend/components/workflow/editors/EditRAGStep.tsx`
*   **Purpose:** A form for configuring the RAG step's `prompt`, `rerank`, `top_k`, and selecting a `vectordb_uuid` from a dropdown.

**2.2.2. Editor Integration**

*   **File to Edit:** `frontend/components/workflow/StepEditor.tsx`
*   **Change:** Conditionally render the `EditRAGStep` component when a step's type is `'rag'`. 
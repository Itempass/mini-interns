## Plan: Implement a Prompt Optimization Engine

**Date:** 2025-07-18
**Author:** AI Assistant

### 1. Summary

This plan outlines the implementation of a "Prompt Optimization Engine" designed to evaluate and improve the performance of `CUSTOM_LLM` steps within workflows. The core of this engine is the "Evaluation Template," a reusable configuration that uses a user's own data (e.g., from their email inbox) to create evaluation datasets. This allows for real-world performance measurement of prompts, moving beyond manual or abstract testing.

The primary goal is to empower users to answer the question: "How well does my prompt perform on my own data?"

### 2. Core Concept: The "Evaluation Template"

An "Evaluation Template" is a saved recipe that defines how to generate a test dataset and measure a prompt's performance against it. It consists of a simple data pipeline that will be configured by the user through a guided UI:

1.  **DISCOVER & CONFIGURE:** The user selects a data source (e.g., "IMAP Emails"). The backend provides a dynamic "Configuration Schema" that tells the frontend exactly which form fields to render (e.g., text inputs for folders, a multi-select dropdown for labels populated with data from the user's inbox).
2.  **SAMPLE & MAP:** The user confirms their configuration. The backend fetches a single sample data item based on this configuration. The frontend displays the fields of this sample, allowing the user to map them to **`input`** and **`ground_truth`**.
3.  **SNAPSHOT:** The user saves the template. The backend performs the full data fetch based on the configuration and saves the result as a static "snapshot" within the template, guaranteeing reproducibility.
4.  **EVALUATE:** (Phase 2) Run the `CUSTOM_LLM` prompt on the input data from the snapshot and compare the generated output against the `ground_truth` to produce an accuracy report.

### 2.1. The "Configuration Schema" Approach

To keep the frontend generic and scalable, we will not hardcode the UI for each data source. Instead, the backend will provide a "UI blueprint" for how to configure a data source.

For example, when configuring an IMAP source, the backend will perform the necessary API calls (e.g., to get all available email labels) and return a schema describing the form fields, their types, and any dynamic options. This allows the frontend to simply render the form without needing any specific knowledge of the data source itself, making the system easy to extend with new sources in the future.

### 3. New Directory Structure

A new top-level directory, `prompt_optimizer/`, will be created to house the core logic for this feature. This will keep the new functionality modular and separated from the existing workflow engine. The `client.py` file will serve as the public-facing API for other services, while `service.py` will contain the internal business logic.

```
mini-interns/
  ├── prompt_optimizer/
  │   ├── __init__.py
  │   ├── client.py         # Public interface for the prompt optimization engine
  │   ├── service.py        # Internal service with core business logic
  │   ├── models.py         # Pydantic models for EvaluationTemplate, EvaluationRun, etc.
  │   ├── database.py       # Database interaction logic
  │   ├── schema.sql        # SQL schema for the new tables
  │   └── exceptions.py     # Custom exceptions
  ├── ... (existing folders)
```

### 4. Backend Implementation

#### 4.1. Database Schema (`prompt_optimizer/schema.sql`)

##### 4.1.1. Integration with Existing Database
The new tables will be created within the existing MySQL database managed by the `db` service in `docker-compose.yaml`. The application's existing database connection, configured via environment variables, will be used. No new database connection is required.

To ensure the tables are created automatically on startup, the `prompt_optimizer/schema.sql` will be executed by extending the current database initialization process. The recommended approach is to modify the existing `scripts/init_workflow_db.py` script to also read and execute our new schema file. This script is already part of the application's startup sequence as defined in `supervisord.conf`.

##### 4.1.2. Schema Definition
We will introduce two new tables. To keep the initial implementation simple, the detailed results of a run will be stored in a JSONB field on the `evaluation_runs` table itself, avoiding the need for a third table for individual test cases.

-   `evaluation_templates`: Stores the user-configured recipes for fetching and mapping data, and caches a static snapshot of the dataset.
-   `evaluation_runs`: Tracks each execution of a template against a specific prompt and stores both a summary and the detailed results.

```sql
-- Stores the user-defined configuration for an evaluation dataset.
CREATE TABLE evaluation_templates (
    uuid UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    data_source_config JSONB NOT NULL, -- e.g., {"tool": "imap.get_emails", "params": {"folder": "INBOX"}}
    field_mapping_config JSONB NOT NULL, -- e.g., {"input_field": "body_cleaned", "ground_truth_field": "labels"}
    cached_data JSONB NOT NULL, -- A snapshot of the data fetched using the config above.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tracks a specific execution of an evaluation template against a prompt.
CREATE TABLE evaluation_runs (
    uuid UUID PRIMARY KEY,
    template_uuid UUID NOT NULL REFERENCES evaluation_templates(uuid) ON DELETE CASCADE,
    workflow_step_uuid UUID NOT NULL, -- The CUSTOM_LLM step being tested
    user_id UUID NOT NULL,
    status VARCHAR(50) NOT NULL, -- e.g., 'running', 'completed', 'failed'
    summary_report JSONB, -- e.g., {"accuracy": 0.85, "total_cases": 200, "passed": 170}
    detailed_results JSONB, -- Stores an array of all test cases: [{input, ground_truth, output, is_match}, ...]
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
```

#### 4.2. IMAP Tool Enhancements (`mcp_servers/imap_mcpserver/src/tools/imap.py`)

To support the DISCOVER & CONFIGURE step, we need to enhance our IMAP client functions:

1.  **`get_all_labels()`**: An existing function that will be used by the backend to populate the `options` for the label filter in the configuration schema.
2.  **`get_emails()`**: A new, more powerful client function to fetch emails.
    -   **Parameters:** `folder: str`, `count: int`, `filter_by_labels: Optional[List[str]]`.
    -   This function will be used for both fetching the sample data and the final snapshot data.

#### 4.3. New API Endpoints

A new set of endpoints will be created, likely in a new file `api/endpoints/prompt_optimizer.py`. These endpoints will use the `prompt_optimizer.client` to interact with the engine's logic.


-   `GET /evaluation/data-sources`: Lists available data sources (e.g., {id: "imap_emails", name: "IMAP Emails"}).
-   `GET /evaluation/data-sources/{source_id}/config-schema`: Returns the dynamic "UI blueprint" for configuring the selected data source. This is where the backend will call things like `get_all_labels` to populate the schema.
-   `POST /evaluation/data-sources/{source_id}/sample`: Fetches a single sample data item based on the user's provided configuration, used for the field mapping step.
-   `POST /evaluation/templates`: Creates the final `EvaluationTemplate`, which includes running the full data fetch and saving the snapshot.
-   `GET /evaluation/templates`: Lists all saved templates for the user.
-   `POST /evaluation/templates/{template_id}/run`: (Phase 2) Initiates an evaluation run.
-   `GET /evaluation/runs/{run_id}`: (Phase 2) Fetches the status and results of an evaluation run.

### 5. Frontend Implementation

#### 5.1. UI Location

The entry point for this feature will be on the `CUSTOM_LLM` step editor (`frontend/components/workflow/editors/EditCustomLLMStep.tsx`). An "Optimize" button will be added.

#### 5.2. New Components (`frontend/components/prompt_optimizer/`)

-   **`CreateEvaluationTemplateModal.tsx`**: A multi-step modal that dynamically builds its UI:
    1.  **Select Data Source:** The user picks from a list of sources provided by the backend.
    2.  **Configure Data Source:** The modal renders a form based on the schema returned from the `/config-schema` endpoint.
    3.  **Map Fields:** The modal calls the `/sample` endpoint and populates dropdowns with the keys from the returned sample object, allowing the user to map `input` and `ground_truth` fields.
    4.  **Save:** The modal calls the final `POST /evaluation/templates` endpoint.
-   **`EvaluationRunnerModal.tsx`**: (Phase 2) This will run the evaluation using the saved template.

### 6. Phased Implementation Plan

#### Completed Work (Foundational Setup)
- **Directory Structure:** The `prompt_optimizer` directory and its constituent files (`client.py`, `service.py`, `models.py`, `database.py`, `schema.sql`, `exceptions.py`) have been created.
- **Database Schema:** The `evaluation_templates` and `evaluation_runs` tables have been defined in `prompt_optimizer/schema.sql`.
- **Database Initialization:** The `scripts/init_workflow_db.py` script has been updated to execute the new schema on application startup.
- **IMAP Client Functions:** The necessary asynchronous functions (`get_all_labels` and `get_emails` with label filtering) have been implemented in `mcp_servers/imap_mcpserver/src/imap_client/client.py`.
- **Core Pydantic Models:** The essential models for the prompt optimizer have been defined in `prompt_optimizer/models.py`.
- **Docker Configuration:** The main `Dockerfile` has been updated to include the `prompt_optimizer` directory in the build.
- **Frontend Scaffolding:**
    - The "Optimize" button has been added to the `EditCustomLLMStep.tsx` component.
    - The `CreateEvaluationTemplateModal.tsx` component has been created and linked to the button.

---
#### Phase 1: Implement Dynamic Data Source Backend
-   **Goal:** Implement the backend logic required for the dynamic, "Configuration Schema" approach.
-   **Tasks:**
    -   Implement a data source registry and abstraction layer in `prompt_optimizer/service.py`. This service will be responsible for returning the config schema and fetching sample data for a given source.
    -   Refactor the API endpoints in `api/endpoints/prompt_optimizer.py` to match the new design (`/data-sources`, `/config-schema`, `/sample`, and `POST /templates`).
    -   Update the `prompt_optimizer/client.py` to be the clean interface for this new service logic.

#### Phase 2: Implement Dynamic Frontend
-   **Goal:** Connect the frontend modal to the new dynamic backend endpoints to create a fully interactive template creation flow.
-   **Tasks:**
    -   Update `CreateEvaluationTemplateModal` to be fully dynamic:
        -   Fetch the list of available data sources to populate the first step.
        -   On selection, fetch the corresponding config schema and dynamically render the configuration form.
        -   On "Next," call the `/sample` endpoint and use the result to populate the field mapping UI.
        -   On "Save," call the final `POST /templates` endpoint and handle the response, including providing a way for the user to download the resulting snapshot for verification.

#### Phase 3: Run Evaluations and Display Results
-   **Goal:** Implement the logic to run an evaluation using a saved template and display the results.
-   **Tasks:**
    -   Extend the `prompt_optimizer.service` to handle the evaluation logic: iterating through the snapshot, calling the LLM for each case, comparing results, and generating a report.
    -   Implement the API endpoints for running an evaluation and fetching the results (e.g., `POST /evaluation/templates/{id}/run`).
    -   Build the `EvaluationRunnerModal` component to trigger runs and display the summary report and detailed results table. 

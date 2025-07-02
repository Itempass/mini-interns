### Title: Refactor: Set LLM models per agent and trigger

### Summary
This pull request refactors the application to remove the global `OPENROUTER_MODEL` setting and introduces a per-agent and per-trigger model configuration. This change provides the flexibility to assign specific LLM models to individual agents and triggers, allowing for task-specific optimization of performance, cost, and capabilities. 

### Changes

*   **Feature:**
    *   Added a `model` field to both `AgentModel` and `TriggerModel`, enabling individual model selection for each agent and trigger. A default model is set to `"google/gemini-2.5-flash-preview-05-20:thinking"`. (see `agent/models.py`)
    *   Updated the database schema (`agent/schema.sql`) and data access functions (`agent/internals/database.py`) to support the new `model` fields.
    *   Implemented a database migration in `scripts/init_db.py` to add the `model` column to the `agents` and `triggers` tables in existing databases and populate a default value.
    *   The agent execution logic in `agent/internals/runner.py` now uses the model specified in `AgentModel`.
    *   Trigger condition evaluation in `triggers/main.py` now uses the model specified in `TriggerModel`.
    *   All relevant API endpoints and types in `api/` have been updated to manage per-agent and per-trigger model settings.
    *   The frontend in `frontend/components/AgentSettings.tsx` now includes input fields for setting the agent and trigger models.
    *   The conversation list in the UI now displays the model used for each agent run (`frontend/components/ConversationsList.tsx`).

*   **Refactor:**
    *   Removed the global `OPENROUTER_MODEL` setting across the application, including from `shared/app_settings.py`, `shared/redis/keys.py`, and the settings UI in `frontend/app/settings/page.tsx`.

*   **Chore:**
    *   Updated `triggers/tests/trigger_condition_test.py` to reflect the architectural changes.
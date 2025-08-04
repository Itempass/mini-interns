### Title: User Balance and Credit System Implementation

**Date:** 2025-07-24

**Status:** Completed

---

### 1. Summary

This document outlines the implementation plan for a new user balance and credit system. The goal is to allow administrators to set a balance for each user and for the system to automatically deduct the cost of LLM and Agent operations from this balance. When a user's balance is depleted (at or below zero), any further costly operations will be blocked, and a descriptive error will be returned. This plan follows a centralized enforcement strategy to ensure robustness and maintainability.

### 2. Prerequisite Reading

To fully understand the context, the developer should be familiar with the following files:

*   `user/internals/database.py`: How user data is currently managed.
*   `agentlogger/src/client.py`: How logs, including costs, are recorded.
*   `workflow/internals/runner.py`: The central execution point for all workflow steps.

---

### 3. Implementation Stages

The implementation will be broken down into the following stages to ensure a smooth and verifiable process.

#### Stage 1: Database and Data Model Updates (Completed)

**Goal:** Extend the user data model to include a balance, with new users receiving a $5.00 default credit.

1.  **Update User Schema Reference:**
    *   **File:** `user/schema.sql`
    *   **Action:** Add a `balance` column to the `users` table. The database-level default will be `0.0` for structural integrity, but the application logic will handle the starting balance for new users.
        ```sql
        -- In user/schema.sql
        balance REAL DEFAULT 0.0,
        ```

2.  **Implement Database Migration and Backfill:**
    *   **File:** `scripts/init_workflow_db.py`
    *   **Action:** Add a migration to add the `balance` column. Crucially, also add a one-time update to set the balance for any existing users to `$5.00`.
    *   **Example Logic:**
        ```python
        # --- Start of User Balance Migration ---
        # First, add the column if it doesn't exist
        cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'balance' AND table_schema = %s", (settings.MYSQL_DATABASE,))
        if cursor.fetchone()[0] == 0:
            logger.info("Adding 'balance' column to 'users' table...")
            cursor.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
            logger.info("Successfully added 'balance' column.")

        # Second, set initial balance for any existing users who are at 0.0
        logger.info("Setting initial $5.00 balance for users with a 0.0 balance...")
        cursor.execute("UPDATE users SET balance = 5.0 WHERE balance = 0.0")
        logger.info(f"{cursor.rowcount} user(s) updated to initial balance.")
        # --- End of User Balance Migration ---
        ```

3.  **Update User Pydantic Model (Primary Default Source):**
    *   **File:** `user/models.py`
    *   **Action:** Add a `balance` field to the `User` model with a default value of `5.0`. This will be the source of truth for all *newly created* users in the application.
        ```python
        # In user/models.py
        class User(BaseModel):
            # ... other fields
            balance: float = 5.0
        ```

#### Stage 2: User Balance Management Logic (Completed)

**Goal:** Create the core functions for reading, setting, and deducting from a user's balance.

1.  **Implement Balance Functions:**
    *   **File:** `user/internals/database.py`
    *   **Action:** Create the following new functions:
        *   `set_user_balance(user_uuid: UUID, new_balance: float) -> User`: Updates the balance for a user.
        *   `deduct_from_balance(user_uuid: UUID, cost: float) -> Optional[User]`: Subtracts from the balance using an atomic `UPDATE users SET balance = balance - %s` query to prevent race conditions.

2.  **Expose Functions via Client:**
    *   **File:** `user/client.py`
    *   **Action:** Add pass-through functions for `set_user_balance` and `deduct_from_balance` to make them accessible to other services.

3.  **Create Admin API Endpoint:**
    *   **File:** `api/endpoints/user.py` (Create this new file if it doesn't exist)
    *   **Action:**
        *   Create a `POST` endpoint `/users/{user_uuid}/balance` to set a user's balance.
        *   Add a dependency to this endpoint that reads a new `ADMIN_USER_IDS` setting from `shared/config.py` and checks if the current user's UUID is in that list, returning a 403 error if not.

#### Verification Point 1: Core Logic Stability (Completed)
**Goal:** Confirm the application runs without errors after adding the backend balance functions but *before* they are actively used.
**Action:**
1.  Start the full application stack.
2.  Log in and navigate through the UI.
3.  Perform a basic, non-costly operation (e.g., save IMAP settings).
**Expected Result:** The application should run smoothly with no new errors in the logs related to the balance system.

#### Stage 3: Implement Cost Controls in Services (Completed)

**Goal:** Integrate the balance check and cost deduction logic into every service that makes LLM calls.

1.  **Define Core Logic Pattern:**
    *   For every service that consumes tokens, the LLM call must be wrapped with our new balance logic.
    *   **The pattern is:**
        1.  **Check Balance:** Before making the LLM call, invoke `user_client.check_user_balance(user_id)`. This will raise an `InsufficientBalanceError` if the balance is depleted, stopping execution.
        2.  **Execute Operation:** Make the LLM call and get the final `cost`.
        3.  **Deduct Cost:** Immediately after a successful call, invoke `user_client.deduct_from_balance(user_id, cost)`. This must happen before returning the result.

2.  **Update All Cost Centers:**
    *   **Action:** Apply the logic pattern described above to the following files. This involves ensuring the `user_id` is passed down to these functions so they can perform the checks and deductions.
    *   **List of files updated:**
        *   `workflow/internals/llm_runner.py`
        *   `prompt_optimizer/llm_client.py`
        *   `workflow/internals/agent_runner.py`

#### Verification Point 2: End-to-End Enforcement (Completed)
**Goal:** Manually test the end-to-end balance deduction and blocking functionality from the backend.
**Action (Positive Balance Test):**
1.  Use a tool like `curl` or Postman to call the admin endpoint (`POST /users/{user_uuid}/balance`) and set your test user's balance to `$5.00`.
2.  In the UI, run a workflow that you know incurs a cost (e.g., one with an LLM step).
3.  Check the `users` table in the database directly to confirm that the balance has been reduced by the expected amount.
**Action (Insufficient Balance Test):**
1.  Use the admin endpoint to set the balance to `$0.00`.
2.  Attempt to run the same costly workflow from the UI.
**Expected Result:** The workflow should fail immediately. Check the browser's developer tools to confirm the API call received a `403 Forbidden` error with a message like "Your balance is depleted."

---

### 4. Final Debugging and Refinement (Completed)

**Goal:** Resolve an issue where the frontend was receiving a generic 500 error instead of the specific 403 "balance depleted" error.

1.  **Problem Identification:**
    *   The `workflow_agent_chat_step` endpoint in `api/endpoints/workflow.py` was using a broad `except Exception` block.
    *   This block was catching the specific `HTTPException(status_code=403)` raised by the runners and replacing it with a generic `HTTPException(status_code=500)`.

2.  **Solution:**
    *   **File:** `api/endpoints/workflow.py`
    *   **Action:** Modified the error handling in the `workflow_agent_chat_step` endpoint to first catch and re-raise any `HTTPException`, preserving its original status code and detail. A general `except Exception` block was kept to handle other unexpected server errors.
        ```python
        # In api/endpoints/workflow.py
        ...
        try:
            # ... main logic ...
        except HTTPException:
            # Re-raise HTTPException directly to preserve status code and detail
            raise
        except Exception as e:
            logger.error(...)
            raise HTTPException(status_code=500, detail="An error occurred during the agent chat turn.")
        ```

### 5.  Cost History Reporting (Completed)

**Goal:** Provide users with a detailed breakdown of their balance deductions in the settings page.

1.  **Enhance Log Database (Completed):**
    *   **File:** `agentlogger/src/schema.sql`
    *   **Action:** Added a `model` column (`TEXT`) to the `logs` table to store which LLM was used for the operation.
    *   **File:** `agentlogger/src/database_service.py`
    *   **Action:** Updated the internal migration logic within the database service to automatically add the `model` column if it doesn't exist, ensuring compatibility with existing installations.

2.  **Update Logging Data Models and Functions (Completed):**
    *   **File:** `agentlogger/models.py`
    *   **Action:** Added an optional `model: str` field to the `LogEntry` Pydantic model.
    *   **File:** `agentlogger/src/database_service.py`
    *   **Action:** Updated the `create_log_entry` and `upsert_log_entry` functions to write the `model` name to the new column in the database.
    *   **Files:** `workflow/internals/llm_runner.py`, `workflow/internals/agent_runner.py`
    *   **Action:** Updated these services to pass the `model` name when creating log entries.
    *   **Note:** `prompt_optimizer/service.py` was investigated but required no changes as it uses a separate logging mechanism.

3.  **Create API Endpoint for Cost History (Completed):**
    *   **File:** `api/endpoints/user.py`
    *   **Action:** Added a `GET /users/me` endpoint to retrieve the current user's details, including their balance.
    *   **File:** `api/endpoints/agentlogger.py`
    *   **Action:**
        *   Created a new endpoint: `GET /logs/costs`.
        *   This endpoint calls a new `get_cost_history(user_id)` function in the `agentlogger` client to query for logs with costs.
        *   It returns a list of cost-related log objects and the total cost.

4.  **Display Cost History Table in Frontend (Completed):**
    *   **File:** `frontend/services/api.ts`
    *   **Action:** Added new functions, `getMe()` and `getCostHistory()`, to call the new API endpoints.
    *   **File:** `frontend/components/settings/BalanceSettings.tsx`
    *   **Action:**
        *   Created a new component to serve as the "Balance" page in the settings section.
        *   The component fetches and displays the user's current balance.
        *   It also fetches the user's cost data and renders it in a table with columns: "Date", "Description", "Model", "Tokens", and "Cost".
    *   **File:** `frontend/components/settings/SettingsSidebar.tsx`
    *   **Action:** Added a "Balance" link to the sidebar to navigate to the new page.
    *   **File:** `frontend/app/settings/page.tsx`
    *   **Action:** Updated the main settings page to render the new `BalanceSettings` component when selected.

#### Verification Point 3: Full UI Verification (Completed)
**Goal:** Verify the UI correctly displays the balance and cost history.
**Action:**
1.  Use the admin endpoint to set a fresh balance for your user (e.g., `$10.00`).
2.  Run a few costly workflows to generate some history.
3.  Navigate to the `Settings -> Balance` page in the UI.
**Expected Result:**
*   The main balance should be displayed correctly (e.g., `$10.00` minus the costs of the workflows you ran).
*   The "Cost History" table should show a row for each workflow run, with the correct cost, model, and token information. 
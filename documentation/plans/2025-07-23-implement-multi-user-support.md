### Title: Multi-User Data Isolation and Architecture Refactoring Plan

**Date:** 2025-07-23

**Status:** Proposed

---

### 1. Summary

This document outlines the necessary architectural changes to transition the platform from a single-user model to a multi-user system. The core principle is ensuring that all user-specific data is strictly isolated and that all services are user-aware. This plan details the required modifications to IMAP connection settings, the centralized logging service, the vector database, and the MCP server architecture to achieve this goal. This plan is designed to be executed by a junior developer, with clear, actionable steps and file references.

### 2. Backward Compatibility for Legacy Authentication Modes

**This plan is fully backward compatible with the existing "no auth" and "password" authentication modes.**

The key to this compatibility is the `get_current_user` dependency defined in `api/endpoints/auth.py`. This function will continue to be the single source of truth for the user's identity.

*   **In "No Auth" or "Password" Mode:** When either of these legacy modes is active, the `get_current_user` function will return a default `User` object with a single, hardcoded UUID.
*   **Impact:** All operations throughout the system (saving settings, writing logs, vectorizing data) will be associated with this one, shared user ID. The system will effectively operate as a single-tenant application, preserving its current behavior. No functionality will be lost for users who do not wish to use the new multi-user Auth0 mode.

### 3. Prerequisite Reading for Implementation

To fully understand the context of these changes, the developer **must** read and understand the following files before beginning implementation.

*   **Core Authentication Logic:**
    *   `api/endpoints/auth.py`: Understand how the `get_current_user` dependency works. This function is the single source of truth for the user's identity across all authentication modes and is central to this entire plan.

---
### 4. Staged Implementation Strategy

To ensure the application remains stable and testable throughout the refactoring process, the implementation **must** be performed in the following stages. Each stage builds upon the last and should be completed and verified before proceeding to the next.

#### Stage 1: Foundational Changes (Schemas & Backward-Compatible Services)
**Status: Completed**
**Goal:** Update the underlying data stores and service functions to be capable of handling user-specific data, while maintaining full backward compatibility with the existing single-user logic. The application must build and run successfully after this stage.
**Actions:**
- [x] **Update `agentlogger` Schema:** Add the `user_id` column as described in the "Centralized Logging" section.
- [x] **Make Core Services Backward-Compatible:** Modify the core service functions in `shared/app_settings.py`, `shared/qdrant/qdrant_client.py`, and `agentlogger` to accept an **optional** `user_uuid`. If the ID is not provided, the functions must fall back to their original, global behavior.

**Testing and Verification (End of Stage 1):**
*   The entire application must start up and run without errors.
*   Test the existing single-user functionality (e.g., saving IMAP settings via the UI). Verify that the application continues to use the old, global Redis keys and Qdrant collections, confirming that the fallback logic is working correctly.

#### Stage 2: Refactor API Endpoints and Direct Call Sites
**Status: Completed**
**Goal:** Connect the user's session to the data layer by updating the "edge" of the application—the API endpoints and other direct callers of the core services.
**Actions:**
1.  **Update All Call Sites:** Work through the detailed file-by-file checklists in the "IMAP Connection", "Centralized Logging", and "Vector Data Isolation" sections. Update every endpoint and internal function listed to get the `user_uuid` from the current context and pass it to the newly modified service functions from Stage 1.

**Testing and Verification (End of Stage 2):**
*   Log in as a new user (User A).
*   Use the UI to save IMAP settings. Use a Redis client to verify that **new, user-specific keys** (e.g., `user:{user_a_uuid}:imap_server`) are created and the old global keys are untouched.
*   Log out and log in as User B. Save different settings and verify a second set of user-specific keys are created.
*   Check that the logs API now only returns logs specific to the logged-in user.

#### Stage 3: Refactor User-Initiated Background Tasks and MCPs
**Goal:** Propagate the user context into background tasks that are initiated by a user's API request and into the MCP servers that are called by the workflow engine.
**Actions:**
1.  **Update Background Tasks:** Implement the changes detailed in the "Refactoring Background Tasks" section, ensuring the `user_uuid` is passed when tasks are initiated and used throughout their execution.
2.  **Update MCP Architecture:** Implement the changes detailed in the "User Context Propagation in MCP Architecture" section for both the workflow engine (caller) and the `imap_mcpserver` (receiver).

**Testing and Verification (End of Stage 3):**
*   As User A, trigger the inbox vectorization background task. Verify that a new Qdrant collection is created specifically for User A and that it is populated with their data.
*   As User B, run a workflow that uses a tool from the `imap_mcpserver` (e.g., `search_emails`). Verify that the MCP server correctly uses User B's IMAP credentials to perform the search.

#### Stage 4: Refactor the Proactive Trigger Service
**Goal:** Convert the single-user email trigger service into a multi-tenant service that polls inboxes for all users who have active, email-triggered workflows.
**Actions:**
1.  **Make Trigger State User-Specific:** Update the Redis key for tracking the last-processed email to be based on `user_uuid`, not `username`.
2.  **Implement Multi-User Polling Loop:** Refactor the main loop in `triggers/main.py` to iterate through all users in the system. For each user, it must load their specific settings and check their inbox.
3.  **Propagate User Context:** Ensure the `user` object or `user_uuid` is passed down through the message processing functions to correctly filter and execute user-specific workflows.

**Testing and Verification (End of Stage 4):**
*   Configure two separate users (User A and User B) with different email accounts and different email-triggered workflows.
*   Send an email to User A. Verify that only User A's workflow is triggered.
*   Send an email to User B. Verify that only User B's workflow is triggered.
*   Check the logs for the trigger service to confirm it is polling both accounts.

#### Stage 5: Finalization and Cleanup
**Goal:** Remove all the backward-compatible fallback logic, making the new user-aware paradigm the only path.
**Actions:**
1.  **Make `user_uuid` Mandatory:** Go back to the core service files from Stage 1 and make the `user_uuid` argument non-optional.
2.  **Remove Fallback Logic & Old Keys:** Delete the code paths that handle the `user_uuid` being `None` and remove the old, global static keys from `shared/redis/keys.py`.

**Testing and Verification (End of Stage 5):**
*   The entire application must start up and run without errors.
*   Run a full regression test of all features for a multi-user environment.
*   Verify that the old global keys in Redis are gone and are no longer being created.

---

### 5. IMAP Connection and Application Settings

**Problem:** Currently, application settings, including sensitive IMAP credentials, are stored globally in Redis. Any user who changes these settings will affect the entire system, making it unsuitable for multiple users.

**Solution:** We will refactor the settings storage mechanism to be user-specific. All settings will be stored under keys that are namespaced by a user's unique ID.

**Execution Steps:**

- [x] **Update Redis Key Generation:**
    *   **File:** `shared/redis/keys.py`
    *   **Action:** Modify the `RedisKeys` class. Instead of using static class variables for keys (e.g., `IMAP_SERVER = "imap:server"`), create methods that accept a `user_uuid` and generate a user-specific key string. For example, create a method `get_imap_server_key(user_uuid: UUID) -> str` which will return a key like `user:{user_uuid}:imap_server`. Apply this pattern for all user-specific settings.

- [x] **Make Settings Functions User-Aware:**
    *   **File:** `shared/app_settings.py`
    *   **Action:**
        *   Modify the `load_app_settings` function to require a `user_uuid` argument. Inside this function, use the new methods from `RedisKeys` (from the previous step) to fetch settings for that specific user.
        *   Modify the `save_app_settings` function to require a `user_uuid` argument. It will use the new key-generation methods to save settings exclusively for that user.

3.  **Update All Call Sites to be User-Aware:**
    *   The developer must update every location where `load_app_settings` and `save_app_settings` are called to pass the user's UUID.
    *   **List of files to update:**
        - [x] `api/endpoints/app_settings.py`: The `GET /settings` and `POST /settings` endpoints must pass the user's UUID from the `get_current_user` dependency.
            *   **Refactor `GET /settings`**:
                1.  This endpoint must be made user-aware by adding the `get_current_user` dependency to its signature.
                2.  It will then call `load_app_settings(user_uuid=current_user.uuid)` to fetch settings for the currently authenticated user.
                3.  **Implement Default Embedding Model Logic**:
                    *   After loading the settings, the endpoint must check if `settings.EMBEDDING_MODEL` is `None`.
                    *   If it is `None`, this indicates a first-time setup for the user. The endpoint will then execute the logic to find the "best available" embedding model by checking `embedding_models.json` against the available API keys in the environment.
                    *   Once the best model is determined, it will be saved to the user's settings by calling `save_app_settings(AppSettings(EMBEDDING_MODEL=best_model), user_uuid=current_user.uuid)`.
                    *   The function will then reload the settings to ensure the response includes the newly set default model.
            *   **Refactor `POST /settings`**:
                1.  This endpoint must also be made user-aware by adding the `get_current_user` dependency.
                2.  It will pass the `current_user.uuid` to the `save_app_settings` function to ensure settings are saved only for the authenticated user.
            *   **Refactor Tone of Voice Endpoints**:
                1.  The `GET /settings/tone-of-voice` and `GET /settings/tone-of-voice/status` endpoints must be updated to use the `get_current_user` dependency.
                2.  They will then use the user's UUID to call the new user-aware `RedisKeys` methods (e.g., `RedisKeys.get_tone_of_voice_profile_key(user_uuid)`).
        - [x] `api/endpoints/connection.py`: The `POST /test_imap_connection` endpoint must pass the user's UUID.
        - [ ] `mcp_servers/imap_mcpserver/src/imap_client/internals/connection_manager.py`: This file's logic must be updated to receive user-specific settings, not call the global loader. This is detailed in the MCP refactoring section.
        - [x] `shared/services/embedding_service.py`: The functions in this service are called by other services that have user context. The `user_uuid` must be passed down to this service so it can load the correct user-specific embedding model.
        - [ ] `triggers/main.py`: The trigger evaluation logic must be made user-aware. It needs to load the settings for the user who owns the trigger it is currently processing.

---

### 6. Centralized Logging (`agentlogger`)

**Problem:** The `logs` table in the agent logger database does not have a column to identify which user a log entry belongs to. This makes it impossible to show users only their own logs.

**Solution:** We will add a `user_id` column to the `logs` table and update the logging service to populate it.

**Execution Steps:**

- [x] **Update the Database Schema:**
    *   **File:** `agentlogger/src/schema.sql`
    *   **Action:** Add a new column named `user_id` to the `CREATE TABLE logs` statement. The data type should be `TEXT` to store the user's UUID as a string. Also, add an index on this new column to ensure that filtering logs by user is fast and efficient.

- [x] **Update the Database Service and Client:**
    *   **Files:**
        *   `agentlogger/src/database_service.py`
        *   `agentlogger/src/client.py`
    *   **Action:**
        *   Modify all functions that create or query logs to accept a `user_id: UUID` argument. This includes `create_log_entry`, `upsert_log_entry`, `get_log_entry`, `get_all_log_entries`, and `get_grouped_log_entries`.
        *   Update the SQL queries within the `database_service.py` functions to use the `user_id` in `WHERE` clauses for filtering, and in `INSERT` statements for saving.

3.  **Update All Call Sites to be User-Aware:**
    *   The developer must update every location where the logger client's functions are called to pass the user's UUID.
    *   **List of files to update:**
        - [x] `api/endpoints/agentlogger.py`: All functions in this file (`list_logs`, `get_log_detail`, etc.) must be updated to use the `get_current_user` dependency and pass the user's UUID to the logger client functions.
        - [x] `api/endpoints/workflow.py`: The `workflow_agent_chat_step` function creates a log entry. It already has access to the user's context and must be updated to pass the `user_id` to `upsert_and_forward_log_entry`.
        - [x] `workflow/internals/llm_runner.py`: The `run` function must be modified to accept the `user_id` and pass it to `save_log_entry`.
        - [x] `workflow/internals/agent_runner.py`: The `run_agent_step` function must be modified to accept the `user_id` and pass it to `save_log_entry`.
        - [x] `workflow/internals/runner.py`: The `_run_step` function must be modified to accept the `user_id` and pass it down to the `llm_runner` and `agent_runner`, as well as to its own direct calls to `save_log_entry`.

---

### 7. Vector Data Isolation (Qdrant)

**Problem:** User-specific data, such as vectorized emails, may be stored in a single, global Qdrant collection, leading to data leakage between users.

**Solution:** We will implement a multi-collection strategy in Qdrant, where each user has their own dedicated collection for their vectorized data.

**Execution Steps:**

- [x] **Implement User-Specific Collections in the Client:**
    *   **File:** `shared/qdrant/qdrant_client.py`
    *   **Action:**
        *   Modify all functions that interact with collections to accept a `user_uuid: UUID` argument. This includes `get_qdrant_client`, `upsert_points`, `count_points`, `semantic_search`, `search_by_vector`, `get_payload_field_distribution`, and `get_diverse_set_by_filter`.
        *   Inside each function, derive a user-specific collection name from the UUID (e.g., `collection_name = f"user_{str(user_uuid).replace('-', '')}"`).
        *   The `get_qdrant_client` (or a new helper function) should be responsible for automatically creating a collection for a user if it doesn't already exist.

2.  **Update All Call Sites to be User-Aware:**
    *   The developer must update every location where the Qdrant client's functions are called to pass the user's UUID.
    *   **List of files to update:**
        - [x] `api/endpoints/agent.py`: The endpoints in this file must use the `get_current_user` dependency and pass the user's UUID to `count_points` and `get_qdrant_client`.
        - [ ] `api/background_tasks/inbox_initializer.py`: The `initialize_inbox` function must accept a `user_uuid` and pass it to `upsert_points`.
        - [ ] `api/background_tasks/determine_tone_of_voice.py`: The `determine_user_tone_of_voice` function must accept a `user_uuid` and pass it to `get_payload_field_distribution` and `get_diverse_set_by_filter`.
        - [ ] `mcp_servers/imap_mcpserver/src/tools/imap.py`: The tool functions in this file must get the `user_uuid` from the request context and pass it to `semantic_search` and `search_by_vector`.

---

### 8. User Context Propagation in MCP Architecture

**Problem:** MCP Servers, like `imap_mcpserver`, perform actions on behalf of a user but are currently designed to be single-user. They use global configurations and have no awareness of *which* user is making a request. This needs to be refactored to support user-specific operations (e.g., accessing the correct inbox).

**Solution:** We will implement a consistent, header-based approach for propagating user context from the calling service (the Workflow Engine) to the receiving MCP Service. This pattern is already in use by the `workflow_agent` and will now be applied to all other MCPs. **Developers must use `workflow_agent/mcp/` as the reference implementation for this pattern.**

**Execution Steps:**

This process involves two parts: the service that *calls* the MCP, and the MCP service that *is called*.

#### Part A: The Caller Service (`workflow` module)

The service that initiates the tool call needs to inject the user's ID into the request headers.

1.  **Inject User ID into MCP Request Headers:**
    *   **File:** `workflow/internals/agent_runner.py` (or the specific file where the `fastmcp` client is used to make HTTP calls to MCPs).
    *   **Action:** Locate the code that executes the tool call to an MCP server. The `fastmcp` client library allows for passing custom headers with the request. When making the call, you must add the user's UUID to the headers. The `agent_runner` has access to the user's context from the `workflow_instance`.
    *   **Example Logic:** The implementation should look something like this (this is conceptual, not literal code):
        ```python
        # In the part of the code that calls the MCP tool
        user_id = workflow_instance.user_id
        mcp_client.call_tool(
            tool_name="...",
            params={...},
            custom_headers={
                "X-User-ID": str(user_id)
            }
        )
        ```
        This ensures that every request sent to an MCP from the workflow engine is tagged with the ID of the user who owns that workflow instance.

#### Part B: The MCP Service (`imap_mcpserver`)

The receiving MCP service needs to be updated to read the user ID from the header and use it to scope all of its operations.

1.  **Implement the Context Extraction Dependency:**
    *   **Action:** Create a new file: `mcp_servers/imap_mcpserver/src/dependencies.py`.
    *   **Content:** Copy the exact contents of `workflow_agent/mcp/dependencies.py` into this new file. This provides the `get_context_from_headers` function, which reads the `X-User-ID` header.

2.  **Make Tools User-Aware:**
    *   **File:** `mcp_servers/imap_mcpserver/src/tools/imap.py`
    *   **Action:** Modify every tool function in this file (e.g., `get_all_labels`, `get_messages_from_folder`). **Follow the example set by `workflow_agent/mcp/tools.py`**.
        *   At the start of each function, call `context = get_context_from_headers()` to retrieve the `UserAndWorkflowContext` object.
        *   Use the `context.user_id` to fetch user-specific application settings: `settings = load_app_settings(user_uuid=context.user_id)`.
        *   Use the `context.user_id` when calling any data services, like the Qdrant client, to ensure you are operating on the correct user's data: `qdrant_client.search(..., user_uuid=context.user_id)`.

3.  **Decouple the `imap_client` from Global State:**
    *   **File:** `mcp_servers/imap_mcpserver/src/imap_client/client.py`
    *   **Action:** This client currently reads settings globally. It must be changed to receive settings explicitly.
        *   Modify the functions that connect to the IMAP server (e.g., `_get_imap_connection`). Instead of them calling `load_app_settings` themselves, they must accept the user-specific `AppSettings` object as an argument.
        *   In the tool functions (from `tools/imap.py`), after you have loaded the user-specific settings, pass this `AppSettings` object directly to the `imap_client` functions. This makes the client stateless and fully dependent on the context provided by the tool, which is now user-aware.

---
### 9. Refactoring Background Tasks for Multi-User Support

**Problem:** The background tasks (`inbox_initializer`, `label_description_generator`, and `determine_tone_of_voice`) are designed for a single user. They use global settings and do not accept a user ID, making them completely unaware of which user's data to process.

**Solution:** Each background task must be refactored to be explicitly user-aware. They will need to be passed a `user_uuid` when they are initiated, and they must use this ID in all subsequent operations.

**Execution Steps:**

1.  **Update Background Task Signatures:**
    *   **Files:**
        *   `api/background_tasks/inbox_initializer.py`
        *   `api/background_tasks/label_description_generator.py`
        *   `api/background_tasks/determine_tone_of_voice.py`
    *   **Action:** Modify the main function in each file (e.g., `initialize_inbox`, `generate_descriptions_for_agent`, `determine_user_tone_of_voice`) to accept a `user_uuid: UUID` as its first argument.

2.  **Make All Operations User-Specific:**
    *   **Action:** Within each of the modified functions, you must use the `user_uuid` to scope all operations to the correct user. This includes:
        *   **Settings:** Calling `load_app_settings(user_uuid=user_uuid)` to get the correct user's IMAP credentials.
        *   **Redis Keys:** Using the refactored `RedisKeys` methods to generate user-specific keys for storing status or results (e.g., `redis_client.set(RedisKeys.get_inbox_status_key(user_uuid), "running")`).
        *   **Qdrant Collections:** Passing the `user_uuid` to the Qdrant client to ensure you are searching and upserting into the user's dedicated collection.
        *   **Database Calls:** Passing the `user_uuid` to any database clients (like the `agent_client` or `workflow_client`) to fetch the correct user's resources.

3.  **Update Task Initiation Logic:**
    *   The developer must update every location where a background task is started to pass the `user_uuid`.
    *   **List of files and specific actions:**
        *   **File:** `api/endpoints/agent.py`
            *   **Functions:** `initialize_inbox_endpoint`, `reinitialize_inbox_endpoint`
            *   **Action:** These endpoints trigger `initialize_inbox`. They must be updated to use the `get_current_user` dependency to obtain the user's UUID and pass it to `initialize_inbox`.
            *   **Function:** `generate_label_descriptions_endpoint`
            *   **Action:** This endpoint triggers `generate_descriptions_for_agent`. It must also use the `get_current_user` dependency and pass the user's UUID to the background task.
            *   **Function:** `trigger_tone_of_voice_analysis_endpoint`
            *   **Action:** This endpoint triggers `determine_user_tone_of_voice`. It must use the `get_current_user` dependency and pass the user's UUID.
        *   **File:** `api/background_tasks/inbox_initializer.py`
            *   **Function:** `initialize_inbox`
            *   **Action:** This task chains a call to `determine_user_tone_of_voice`. It must be updated to pass along the `user_uuid` it received when it was started. 

---
### 10. Refactoring the Proactive Trigger Service

**Problem:** The email trigger service (`triggers/main.py`) is architected for a single, global user. It polls one inbox based on global settings. To support multiple users, it must be fundamentally changed to poll every user's inbox individually.

**Solution:** We will refactor the trigger service into a multi-tenant polling engine. The main loop will be redesigned to iterate through all users, load their individual settings, and check their respective inboxes for new mail that could trigger their specific workflows.

**Execution Steps:**

1.  **Update Redis Key for Trigger State:**
    *   **File:** `shared/redis/keys.py`
    *   **Action:** The current `get_last_email_uid_key` method accepts a `username`. This is not a reliable unique identifier. Modify this method to accept a `user_uuid: UUID` instead, ensuring the trigger's state is reliably tied to a specific user account.

2.  **Implement Multi-User Polling Loop:**
    *   **File:** `triggers/main.py`
    *   **Action:**
        *   Remove the single, global `while True:` loop's dependency on `load_app_settings()`.
        *   The main loop should now first query the database to get a list of all users (e.g., using a new function like `user_client.get_all_users()`).
        *   The loop will then iterate over this list of users. Inside the loop, for each `user`:
            *   Load the user-specific IMAP settings by calling `load_app_settings(user_uuid=user.uuid)`.
            *   If the settings are not configured for that user, skip to the next user.
            *   Use the new `RedisKeys.get_last_email_uid_key(user_uuid=user.uuid)` to get the last processed UID for that specific user.
            *   Connect to the user's mailbox and check for new emails.
            *   If new messages are found, call the `process_message` function, making sure to pass the `user` object.

3.  **Make Message Processing User-Aware:**
    *   **File:** `triggers/main.py`
    *   **Action:**
        *   The `process_message` function must be modified to accept the `user: User` object from the main polling loop.
        *   It will no longer need to call `get_current_user()`, as the user context is now provided directly.
        *   All subsequent calls within `process_message` (e.g., to `workflow_client`, `trigger_client`, etc.) must use the `user.uuid`. 
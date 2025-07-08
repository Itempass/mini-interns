# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.3] - 2025-07-09

### Added
- **Authentication**: Added a simple password-based authentication layer to protect the application.
- **Vectorization Data Versioning**: Implemented a versioning system for the vector database to automatically trigger re-vectorization when the data structure changes.
- **Dynamic Agent Settings UI**: Added a new type of agent settings page with a simpler interface. This will initially mainly be used for templated agents. The interface adaps based on the json in the template. 
- **Agent Template Versioning**: Added `template_id` and `template_version` to agent templates for better traceability and future migrations.
- **Comprehensive Email Indexing**: The inbox vectorization process now fetches emails from both "Sent Mail" and "All Mail" to create a more complete dataset for analysis.
- **Tool Execution in Trigger Conditions**: The trigger evaluation system can now execute tools (e.g., `find_similar_threads`) in real-time to make more informed decisions.
- **Tone of Voice Analysis**: Introduced a new service to analyze the user's email history and generate a detailed tone of voice profile, enabling agents to draft replies that match the user's communication style.
- **UI/UX**: Added a welcome screen for new users, an improved agent creation flow that prioritizes templates, and better status polling and display for background tasks like tone-of-voice analysis.

### Changed
- **`find_similar_threads` Tool**: The tool's output has been changed from a JSON object to a clean, directly usable markdown string to simplify agent prompts.
- **Startup/Shutdown**: Replaced the deprecated `on_event("startup")` with the `lifespan` context manager for more reliable startup and shutdown event handling in the backend. (note: is still a dirty fix (the lifespan runs 4 times because we have 4 workers).)

### Fixed
- **API Keys**: The application no longer treats the default `"EDIT-ME"` value as a valid API key.
- **Agent Templates**: Fixed the `Email Labeler` agent template which included incorrect tools by default.
- **Agent Templates**: Corrected the default tool order in the `Repetitive Emails Emaildrafter` agent template.
- **Agent Tool Order**: Corrected a bug that caused the order of an agent's required tools to be scrambled upon saving.
- **Backend Status Checker**: The frontend `BackendStatusChecker` is now properly loaded first (used to be a race condition with other api calls, which could cause the frontend to crash before the backend status checker overlay was shown)
- **Language-Agnostic IMAP Folders**: Implemented RFC 6154 to dynamically discover special-use folders (e.g., `\Sent`, `\All`), resolving a major issue for users with non-English email clients.
- **Inbox Initialization**: The inbox initialization process now correctly reports a "failed" status if vectorization does not succeed for any threads, preventing silent failures.
- **MCP Inspector Port Conflict**: Commented out the MCP Inspector ports by default in `docker-compose.yaml` to prevent port conflicts when running multiple instances on one server.
- **Feedback Submissions**: Feedback submissions now include the full conversation log, providing more context for developers.
- **UI**: The application now correctly notifies users of new releases, even when running a development (`-dev`) version.
- **UI**: The "App Password" help button in the settings UI is now more prominent.
- **UI**: Corrected the name of the "Email Labeler" agent template and changed the text in the top bar from "Agent" to "Agents".
- **IMAP Tool**: Corrected a variable name in the `find_similar_threads` tool.
- **IMAP UID**: Fixed a race condition when resetting the last email UID during the trigger loop by linking the UID to the specific email account.

### Refactor
- **UI and Background Task Handling**: Improved the user experience for tone-of-voice analysis with status polling and enhanced background task management.
- **Email Indexing**: Refactored the email indexing process to support fetching from multiple mailboxes and added `type` and `contains_user_reply` metadata to messages and threads.
- **Agent Creation**: Improved the agent creation modal to prioritize using templates.

## [0.0.2] - 2025-07-02

### Added
- **Agent Runner:** Dynamically calculate `max_cycles` in the agent runner based on the number of tools.
- **Prompts:** Added a `<<MY_EMAIL>>` placeholder for use in agent and trigger prompts.
- **Frontend:** Added a backend health check and loading screen to prevent users from seeing errors while the backend starts up.
- **Models:** Added a `model` field to both `AgentModel` and `TriggerModel`, enabling individual model selection for each agent and trigger.
- **Logging:** Implemented an API-based logging system to replace direct database access.
- **UI:** Added an IMAP connection status indicator to the main sidebar.
- **UI:** Enhanced the settings page with visual indicators for unsaved changes and a help panel for Google App Passwords.
- **Security:** Implemented encryption for sensitive application settings like `IMAP_PASSWORD` and `OPENROUTER_API_KEY` (note: `OPENROUTE_API_KEY` was moved to .env in another change.).
- **Embeddings:** Added support for multiple embedding models (OpenAI and Voyage), selectable by the user.
- **Embeddings:** Implemented an interruptible inbox vectorization process that can be gracefully stopped and restarted.
- **Embeddings:** Added automatic inbox vectorization, triggered upon successful IMAP connection.
- **UI:** The conversation list now displays the LLM model used for each agent run.
- **UI:** Added a top bar that appears when a new version of the application is available.
- **Agents:** Added simple agent templates for common use cases.

### Changed
- **Triggers:** Triggers now ignore emails sent by the configured user email address to prevent processing sent items.
- **Embeddings:** Reranking is now skipped if the selected embedding model is from OpenAI.
- **Triggers:** The "bypass" setting now only bypasses the trigger prompt, not the entire trigger condition check.
- **UI:** Clarified the active/paused status indicator for agents in the sidebar to avoid confusion with buttons.
- **UI:** Added instructional text to the tool list to indicate that tools can be reordered via drag-and-drop.
- **UI:** Improved the layout of the tool list and added tooltips for better usability.

### Fixed
- **Agent Runner:** Fixed a `TypeError` when processing tool call results from the MCP.
- **Build:** Resolved a Zod-related build issue on Coolify where environment variables were not available at build time.
- **Promtail:** Fixed Promtail configuration and updated Docker setup to use a dedicated Dockerfile for Promtail.
- **Embeddings:** The embedding service now correctly re-initializes when the embedding model is changed.
- **Logging:** Corrected the default value for the `agentlogger` enabled/disabled flag.
- **IMAP:** Changing the IMAP username now correctly resets the UID tracking to ensure new emails are fetched.
- **IMAP:** The IMAP MCP server now consistently uses the latest IMAP credentials.
- **Security:** Ensured the encryption key for settings is persistent across restarts.
- **UI:** The settings field for the OpenRouter model is now displayed correctly.

### Refactor
- **Models:** Removed the global `OPENROUTER_MODEL` setting in favor of per-agent and per-trigger model configurations.
- **Storage:** Removed the obsolete Redis-based storage system for agent settings. All configurations are now managed in the database.
- **Logging:** Centralized logging operations through dedicated API endpoints, removing direct database access from the agent.

## [0.0.1] - 2025.06.30

### Added
- Initial project versioning system with a `VERSION` file.
- `/api/version` endpoint to expose the application version.
- Version display on the frontend settings page.
- Created `CHANGELOG.md` to document changes.

[Unreleased]: https://github.com/Itempass/mini-interns/compare/v0.0.3...HEAD
[0.0.3]: https://github.com/Itempass/mini-interns/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/Itempass/mini-interns/compare/v0.0.1...v0.0.2 
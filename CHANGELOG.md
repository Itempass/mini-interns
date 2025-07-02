# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.2] - 2025-07-02

### Added
- **Agent Runner:** Dynamically calculate `max_cycles` in the agent runner based on the number of tools.
- **Prompts:** Added a `<<MY_EMAIL>>` placeholder for use in agent and trigger prompts.
- **Frontend:** Added a backend health check and loading screen to prevent users from seeing errors while the backend starts up.
- **Models:** Added a `model` field to both `AgentModel` and `TriggerModel`, enabling individual model selection for each agent and trigger.
- **Logging:** Implemented an API-based logging system to replace direct database access.
- **UI:** Added an IMAP connection status indicator to the main sidebar.
- **UI:** Enhanced the settings page with visual indicators for unsaved changes and a help panel for Google App Passwords.
- **Security:** Implemented encryption for sensitive application settings like `IMAP_PASSWORD` and `OPENROUTER_API_KEY`.
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

[Unreleased]: https://github.com/Itempass/mini-interns/compare/v0.0.2...HEAD
[0.0.2]: https://github.com/Itempass/mini-interns/compare/v0.0.1...v0.0.2 
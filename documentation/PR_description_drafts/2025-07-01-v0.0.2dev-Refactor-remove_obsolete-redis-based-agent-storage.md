# Refactor: Remove Deprecated Redis-Based Agent Storage

## Summary

This refactoring removes the obsolete Redis-based storage system for agent settings. All agent and trigger configurations, including trigger conditions and filter rules, are now exclusively managed through the existing database-driven models. This change eliminates redundant code, removes the potential for data inconsistency between Redis and the database, and simplifies the overall architecture.

## Changes

### API and Data Model Cleanup

*   **Chore: Removed Redis-dependent API endpoints.**
    *   Deleted the `GET /agent/settings` and `POST /agent/settings` endpoints. These were coupled to the legacy Redis storage model.

*   **Chore: Deleted unused Pydantic and TypeScript models.**
    *   Removed the `AgentSettings` model from both the Python API and the frontend service, as it is no longer required.

### Trigger System Refactoring

*   **Refactor: Removed legacy trigger and migration logic.**
    *   Deleted `triggers/old_agent.py`, `triggers/migration.py`, and the helper file `triggers/agent_helpers.py`, which were all part of the old system.
    *   Removed the call to the obsolete database migration function from the startup sequence in the main trigger loop.

### Configuration Cleanup

*   **Chore: Removed obsolete Redis key definitions.**
    *   Deleted the definitions for `AGENT_INSTRUCTIONS`, `AGENT_TOOLS`, `TRIGGER_CONDITIONS`, `FILTER_RULES`, and `DEFAULT_AGENT_ID`.


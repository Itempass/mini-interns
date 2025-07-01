**Title:** Feature: Add support for multiple embedding models and interruptible vectorization

**Summary:**
This pull request introduces two major enhancements: the ability for users to select from multiple embedding models (OpenAI and Voyage) and a mechanism to gracefully interrupt and restart the inbox vectorization process. These changes provide more flexibility and improve the user experience when managing embeddings.

**Changes:**

*   **Feature: Selectable Embedding Models**
    *   **Backend:**
        *   The `EmbeddingService` in `shared/services/embedding_service.py` has been refactored to dynamically load embedding providers (OpenAI, Voyage) and models based on a new setting stored in Redis.
        *   Model configurations, including provider, vector size, and token limits, are now defined in a new `shared/embedding_models.json` file.
        *   A new script, `scripts/set_initial_embedding_model.py`, runs on startup to automatically select the best available model based on configured API keys. This is integrated into the startup sequence in `supervisord.conf`.
        *   Qdrant collection management in `shared/qdrant/qdrant_client.py` now dynamically retrieves the vector size from the active embedding model.
        *   API key for OpenRouter is now sourced directly from `shared.config.settings` instead of being stored in Redis, improving configuration management (`triggers/main.py`, `triggers/old_agent.py`).
    *   **Frontend:**
        *   The settings page (`frontend/app/settings/page.tsx`) now features a dropdown menu for selecting the desired embedding model.
        *   Changing the model prompts the user for confirmation, as it requires deleting existing vectors and re-vectorizing the inbox.
        *   The UI displays a warning if the user selects a model for which the corresponding API key is not configured.
        *   The `getSettings` function in `frontend/services/api.ts` was updated to fetch the list of available embedding models from the backend.

*   **Feature: Interruptible Inbox Vectorization**
    *   **Backend:**
        *   The background vectorization process in `api/background_tasks/inbox_initializer.py` now checks for a Redis flag (`inbox:vectorization:interrupted`) before processing each batch of emails.
        *   The "Re-vectorize" function now sets this flag, ensuring that any ongoing vectorization job is gracefully stopped before the new one begins.
        *   A new Redis key `INBOX_VECTORIZATION_INTERRUPTED` was added to `shared/redis/keys.py`.
    *   **Testing:**
        *   Added isolated unit tests in `api/tests/test_inbox_initializer_isolated.py` to verify that the interruption signal correctly halts the vectorization loop.

*   **Chore: Configuration and Testing**
    *   Added `pytest.ini` to configure `asyncio_mode` for tests.
    *   Removed the `OPENROUTER_API_KEY` from the user-facing settings page and Redis storage, treating it as a server-side environment variable. 

*   **Chore: Cleanup of .env file**
    *   Removed unused variables
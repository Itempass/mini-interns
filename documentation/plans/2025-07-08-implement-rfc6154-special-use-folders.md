# Plan: Implement RFC 6154 (IMAP Special-Use Folders)

**Date**: 2025-07-08
**Author**: Gemini
**Status**: Proposed

## 1. Executive Summary

The current IMAP client implementation relies on hardcoded, English-specific folder names (e.g., `[Gmail]/Sent Mail`, `[Gmail]/All Mail`). This approach fails for users with non-English language settings in their email accounts, as folder names are localized.

This plan outlines the steps to refactor the IMAP client to use the RFC 6154 "SPECIAL-USE" extension. This extension allows us to programmatically identify standard folders (Sent, Drafts, All Mail, etc.) using language-agnostic attributes (`\Sent`, `\All`, `\Drafts`). This change will make our email integration robust across different languages and email providers that support the standard.

## 2. Problem Analysis

- **Hardcoded folder names**: `[Gmail]/Sent Mail`, `[Gmail]/All Mail`, `[Gmail]/Drafts`, and `INBOX` are used throughout the backend.
- **Affected modules**:
    1. `mcp_servers/imap_mcpserver/src/imap_client/`: The core client used for most IMAP operations.
    2. `api/background_tasks/inbox_initializer.py`: Uses the core client for bulk fetching.
    3. `triggers/main.py`: The main polling loop uses the `imap-tools` library and hardcodes `initial_folder='INBOX'`, which can be localized.
- **Impact**: Core functionality is unreliable for international users. The trigger system may fail to detect any new emails.

## 3. Proposed Solution

We will create a centralized `FolderResolver` class responsible for mapping special-use attributes to actual folder names. To keep connection-related logic encapsulated, this class will be implemented directly within `connection_manager.py`. All parts of the application will use this resolver instead of hardcoded strings.

This approach ensures thread safety, as each call to `imap_connection()` will create a new, isolated IMAP connection and a corresponding `FolderResolver` instance, preventing any sharing of `imaplib` objects across threads.

## 4. Actionable Implementation Plan

### Phase 1: Implement the Folder Resolver in the Connection Manager

1.  **Modify File**: `mcp_servers/imap_mcpserver/src/imap_client/internals/connection_manager.py`.

2.  **Implement `FolderResolver` Class (within `connection_manager.py`)**:
    -   It will be initialized with an active `imaplib.IMAP4_SSL` connection.
    -   **`_discover_folders()` method**:
        -   On initialization, it will call `mail.list()` to get all folders and their attributes.
        -   It will parse the response to find folders with `\Sent`, `\All`, `\Drafts`, `\Junk`, `\Trash` attributes.
        -   It will store this mapping in an instance dictionary (e.g., `self.folder_map = {'\\Sent': 'Envoyés', ...}`).
    -   **Public Getter Methods**:
        -   `get_folder_by_attribute(attribute: str) -> str`: Returns the real folder name for a given attribute (e.g., `\Sent`).
        -   It will include robust fallback logic: if a special-use folder isn't found, it will revert to pattern-matching and guessing for common English names as a last resort.
    -   **Caching**: The resolved names will be cached for the lifetime of the `FolderResolver` instance to avoid redundant `LIST` commands on the same connection.

### Phase 2: Integrate Resolver into Connection Management

1.  **Update `IMAPConnectionManager`** (in `connection_manager.py`):
    -   Modify the `connect` context manager to instantiate `FolderResolver` after a successful login.
    -   Yield both the `mail` connection and the `resolver` instance.
    -   Example: `yield mail, resolver`

2.  **Update `imap_connection()`** (in `connection_manager.py`):
    -   Update the convenience function to match the new return signature, making the resolver easily accessible.
    -   Example: `with imap_connection() as (mail, resolver):`

### Phase 3: Refactor Core IMAP Client (`client.py`)

For each function that uses a hardcoded folder name, do the following:

1.  **Update `with imap_connection() as mail:` to `with imap_connection() as (mail, resolver):`**.
2.  Replace hardcoded strings with calls to the resolver.

**Target Functions:**

-   `_find_uid_by_message_id()`: Use `resolver.get_folder_by_attribute('\\All')`, `resolver.get_folder_by_attribute('\\Sent')` etc. to build the `mailboxes_to_search` list.
-   `_get_message_by_id_sync()`: Same as above.
-   `_get_complete_thread_sync()`: Replace `'[Gmail]/All Mail'` with `resolver.get_folder_by_attribute('\\All')`.
-   `_get_user_signature()`: Replace `'[Gmail]/Sent Mail'` with `resolver.get_folder_by_attribute('\\Sent')`.
-   `_draft_reply_sync()`: Replace `_find_drafts_folder(mail)` with `resolver.get_folder_by_attribute('\\Drafts')`.

**Public API Functions:**

-   `get_recent_inbox_messages()`: `INBOX` is usually safe, but can be resolved for consistency.
-   `get_recent_sent_messages()`: Change the hardcoded `"[Gmail]/Sent Mail"` to use the resolver via an internal function that accepts the attribute.

### Phase 4: Refactor Bulk Threading & Background Tasks

1.  **Update `_fetch_bulk_threads_sync()`** (`internals/bulk_threading.py`):
    -   Update the function to accept the `resolver` instance.
    -   Modify the signature to accept a special-use attribute instead of a mailbox name: `special_use: str`.
    -   Inside the function, use the resolver to get the correct folder name based on the `special_use` attribute.
    -   Default `source_mailbox` will be resolved from `special_use='\\Sent'`.
    -   The hardcoded `'[Gmail]/All Mail'` will be resolved from `special_use='\\All'`.

2.  **Update `fetch_recent_threads_bulk()`** (`internals/bulk_threading.py`):
    -   Modify the `run_in_executor` call to pass the resolver instance to `_fetch_bulk_threads_sync`.

3.  **Update `initialize_inbox()`** (`api/background_tasks/inbox_initializer.py`):
    -   This task calls `get_recent_threads_bulk`.
    -   Update the calls to pass `special_use='\\Sent'` and `special_use='\\All'` instead of hardcoded mailbox names.

### Phase 5: Refactor the Trigger Polling Loop

1.  **Modify `triggers/main.py`**:
    -   Before the `while True:` loop, establish a short-lived connection using our own `imap_connection` context manager to get access to the `FolderResolver`.
    -   Use `resolver.get_folder_by_attribute('\\Inbox')` to discover the correct, potentially localized, name for the inbox.
    -   Store this resolved inbox name in a variable.
    -   In the polling loop, update the `imap-tools` call to use the resolved name:
        `with MailBox(...).login(..., initial_folder=resolved_inbox_name) as mailbox:`
    -   This ensures the polling loop always looks in the correct folder without being tightly coupled to our main client's connection management during the poll itself.

### Phase 6: Update Tests

-   Modify all tests in `mcp_servers/imap_mcpserver/tests/` and potentially `triggers/tests` that use hardcoded folder names.
-   Patch the `FolderResolver` to return consistent, mock folder names during testing. This ensures tests are not dependent on a live connection and are deterministic.

## 5. Timeline & Milestones

-   **Day 1**: Implement `FolderResolver` and integrate it into the connection manager.
-   **Day 2**: Refactor `client.py` and its unit tests.
-   **Day 3**: Refactor `bulk_threading.py`, `inbox_initializer.py` and their related tests.
-   **Day 4**: Refactor `triggers/main.py` to use the resolver for the inbox folder.
-   **Day 5**: Full integration testing and bug fixing. 
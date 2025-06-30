**Title:** Feat: Implement Automatic Inbox Vectorization

**Summary:**

This pull request introduces a feature to automatically trigger the inbox vectorization process as soon as valid IMAP credentials are provided and verified. This replaces the previous button to initiate this.

**Changes:**

*   **Feature:**
    *   Added an `attemptAutoVectorization` function to automatically start the vectorization process upon successful IMAP connection testing. This check is performed when the settings page loads and whenever the connection settings are updated (`frontend/app/settings/page.tsx`).
    *   Vectorization is initiated if the current inbox status is `not_started` or `failed`.

*   **Chore:**
    *   Removed the manual "Start Inbox Vectorization" button and its corresponding handler (`handleVectorize`), as the process is now automated (`frontend/app/settings/page.tsx`).
    *   Relocated the "Inbox Vectorization" section on the settings page for improved layout and user experience (`frontend/app/settings/page.tsx`).
    *   The "Re-vectorize Inbox" button has been redesigned as a smaller "Re-vectorize" button located next to the status indicator (`frontend/app/settings/page.tsx`).
    *   Reduced the polling interval for checking the vectorization status from 5 to 3 seconds for more responsive UI feedback (`frontend/app/settings/page.tsx`). 
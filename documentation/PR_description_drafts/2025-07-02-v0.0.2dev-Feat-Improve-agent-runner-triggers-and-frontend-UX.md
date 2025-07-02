**Title:** Feat: Improve agent runner, triggers, and frontend UX

**Summary:**

This pull request introduces several enhancements to the agent runner, trigger mechanism, and frontend user experience. Key changes include dynamic max cycles calculation for agents (how many times we go through the agent for loop before stopping in case agent gets stuck), a new placeholder for the user's email, prevention of trigger on sent emails, and a backend status checker on the frontend to improve initial load (so users don't see an error screen if backend is still starting up).

**Changes:**

*   **Feature:**
    *   Dynamically calculate `max_cycles` in the agent runner based on the number of tools, replacing the hardcoded value (`agent/internals/runner.py`).
    *   Added a `<<MY_EMAIL>>` placeholder for use in agent and trigger prompts (`agent/internals/runner.py`, `triggers/main.py`, `frontend/components/AgentSettings.tsx`).
    *   Added a backend health check and loading screen to the frontend to prevent users from seeing errors while the backend starts up (`frontend/components/BackendStatusChecker.tsx`, `frontend/app/page.tsx`, `frontend/services/api.ts`).
    *   Triggers now ignore emails sent by the configured user email address to prevent processing sent items (`triggers/main.py`).

*   **Chore:**
    *   Updated the `README.md` roadmap. 
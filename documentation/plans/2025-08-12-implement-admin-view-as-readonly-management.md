## Implement admin "View as" read-only management (Option B)

### Goal
- Allow admins (users listed in `ADMIN_USER_IDS`) to open the existing workflows interface for any user in a read-only mode.
- Entry point: the existing `Management` page (`/management`) gets a "View as" button per user that opens a new tab.
- Security: Only admins can use this; management routes are read-only and cannot mutate data.

### Scope
- Backend: Add a dedicated `/management` router exposing read-only endpoints to fetch another user's workflows (and later, logs), protected by admin checks.
- Frontend: Extend `Management` page with "View as" per user. Add a read-only workflows view that reuses existing components but disables all write actions when viewing another user.
- No changes to write endpoints or workflow persistence needed.

---

### Backend changes

1) Add new router: `api/endpoints/management.py`
   - Prefix: `/management`
   - Protection: All routes require `Depends(get_current_user)` and `Depends(is_admin)` (reuse `is_admin` from `api/endpoints/user.py`).
   - Read-only endpoints:
     - `GET /management/users/{user_uuid}/workflows`
       - Returns: `List[workflow.models.WorkflowModel]`
       - Implementation: `return await workflow_client.list_all(user_id=user_uuid)`
     - `GET /management/users/{user_uuid}/workflows/{workflow_uuid}`
       - Returns: `workflow.models.WorkflowWithDetails`
       - Implementation: `return await workflow_client.get_with_details(workflow_uuid, user_id=user_uuid)`
   - Logs (mandatory):
     - `GET /management/users/{user_uuid}/agentlogger/logs/grouped?limit&offset&workflow_id&log_type`
     - `GET /management/users/{user_uuid}/agentlogger/logs/{log_id}`
     - `GET /management/users/{user_uuid}/agentlogger/logs/costs`
     - All call existing agentlogger client functions, passing `user_id=str(user_uuid)`.
     - No write endpoints under `/management` (e.g., no review POST); keep management read-only.

2) Wire router in `api/main.py`
   - `app.include_router(management.router, tags=["management"])`

3) Data models and DB access
   - Reuse existing `workflow.client` and `workflow.internals.database` functions which already accept `user_id`.
   - No schema changes.

4) Security and invariants
   - Only `GET` endpoints under `/management` (workflows and logs).
   - `is_admin` dependency enforces admins-only. Uses `ADMIN_USER_IDS` from `shared/config.py` via `settings`.
   - Workflows write endpoints remain unchanged and continue to scope by `current_user.uuid`.
   - Logs write endpoints (e.g., adding a review) are not exposed under `/management` and remain outside the admin view. Client-side also blocks non-GET in admin view.

5) Tests (API)
   - Add unit tests for:
     - 403 for non-admin access to `/management/...` endpoints (workflows and logs).
     - 200 for admins; responses match shapes of standard endpoints.
     - Requests for non-existent users or workflows return 404 as appropriate from client functions.
     - Logs endpoints return grouped logs, single log, and costs for the target user.

Files to edit/create (backend):
- Create: `api/endpoints/management.py`
- Edit: `api/main.py`
- Tests: `api/tests/unit/test_management_endpoints.py` (new)

---

### Frontend changes (no component edits; reuse as-is)

1) Management page UI: `frontend/app/management/page.tsx`
   - Add a new column/button "View as" for each user row.
   - Clicking opens a new tab to a helper route: `/workflows/management?user_id=<uuid>`.
   - Keep existing admin functionality (balance updates) intact.

2) Read-only management entry page (client, uses sessionStorage)
   - Create `frontend/app/workflows/management/page.tsx` as a client component that:
     - Reads `user_id` from `useSearchParams()`.
     - Sets `sessionStorage.admin_view_user_id = <uuid>` and `sessionStorage.admin_view_mode = 'true'`.
     - Navigates to `/workflows` via `router.replace('/workflows')`.
   - Optional exit page: `frontend/app/workflows/management/clear/page.tsx` that clears these keys and redirects back to `/workflows`.

3) Client fetch rewrite using sessionStorage (no UI or component changes)
   - File: `frontend/services/api.ts` (in `apiFetch`):
     - If `typeof window !== 'undefined'` and method is GET and `sessionStorage.admin_view_user_id` exists:
       - If URL starts with `/api/workflows`, rewrite to `/api/management/users/<id>/workflows...` (preserve the rest of path and query).
       - If URL starts with `/api/agentlogger`, rewrite to `/api/management/users/<id>/agentlogger/...`.
     - If method is not GET and `sessionStorage.admin_view_mode === 'true'`, throw an error with status 403 and a clear message to enforce read-only from the client side.
   - Tokens and other headers remain handled by `apiFetch` as today; only the URL is rewritten for read calls when in admin view.

4) No changes to components
   - We intentionally reuse `frontend/app/workflows/page.tsx` and all nested components as-is.
   - The UI may still show editable controls; admins understand this is a read-only view.
   - Safety is enforced by client-side read-only blocking and backend read-only `/management` endpoints.

5) Auth propagation
   - Existing `apiFetch` already attaches Auth0 Bearer tokens when in Auth0 mode.
   - `/management` endpoints are server-guarded by `is_admin`; no client-side role logic is relied upon for security (only for hiding buttons).

Files to edit/create (frontend):
- Edit: `frontend/app/management/page.tsx` (add View as button)
- Create: `frontend/app/workflows/management/page.tsx` (sets sessionStorage and redirects)
- Create (optional): `frontend/app/workflows/management/clear/page.tsx` (clears sessionStorage)
- Edit: `frontend/services/api.ts` (GET rewrites to `/management` for workflows and logs; block non-GET when in admin view)

---

### API shapes (reference)

- `GET /management/users/{user_uuid}/workflows`
  - 200 → `Workflow[]` (same as `GET /workflows`)
  - 403 → non-admin

- `GET /management/users/{user_uuid}/workflows/{workflow_uuid}`
  - 200 → `WorkflowWithDetails` (same as `GET /workflows/{id}`)
  - 404 → not found
  - 403 → non-admin

Phase 2 (optional): logs endpoints mirror existing shapes under `/agentlogger`.

---

### Acceptance criteria
- Only users in `ADMIN_USER_IDS` can access `/management` routes; non-admins receive 403.
- From `/management`, clicking "View as" for a user opens a new tab that redirects to `/workflows` and loads that user’s workflows and logs (sessionStorage-driven) without any component changes.
- UI can remain fully interactive-looking; however, client blocks non-GET requests in admin view, and backend management endpoints are GET-only.
- No ability to mutate another user’s data via management routes or via write calls while the admin-view session flag is set (e.g., posting log reviews is blocked in admin view).
- Existing non-management functionality remains unaffected for normal users.

### Testing plan
- Frontend manual tests:
  - Admin: open `/management`, click View as, confirm workflows load; verify all write actions are disabled; banner present.
  - Non-admin: cannot navigate to `/management` (middleware/redirect already handled via backend checks + UI hiding if desired).

### Rollout
- Behind configuration of `ADMIN_USER_IDS`.
- Ship Phase 1 (workflows). Phase 2 (logs) optional if we need full parity in the right panel.

### Risks and mitigations
- UI still calling write endpoints in read-only mode → Mitigate by gating all write flows with `readonly` checks and removing UI controls.
- Confusion between admin and manager roles → We explicitly use existing `ADMIN_USER_IDS` as per request.

---

### References
- Auth and role check: `api/endpoints/auth.py`, `api/endpoints/user.py:is_admin`, `shared/config.py`.
- Workflow endpoints and models: `api/endpoints/workflow.py`, `workflow/client.py`, `workflow/internals/database.py`, `workflow/models.py`.
- Frontend workflows UI and services: `frontend/app/workflows/page.tsx`, `frontend/services/workflows_api.ts`.
- Management page: `frontend/app/management/page.tsx`.
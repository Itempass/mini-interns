## Strengthen `user` module separation and balance atomicity

### Context
We want all user-related concerns (authentication, registration, user discovery, balances/credits, admin checks) to live inside the `user` package, with other services acting as thin callers. Today most of this is in good shape, but a few responsibilities leak into API endpoints, and balance deduction is not fully atomic.

### Goals
- Ensure strict separation of concerns: all user logic is implemented in `user`, and other layers (endpoints, runners) call it.
- Make balance deduction atomic and race-safe.
- Centralize password-mode auth helpers and admin checks in `user`.
- Align configuration and defaults, remove ambiguity.

### Non-goals
- Replacing the existing authentication modes (Auth0 vs password vs none).
- Building new user-facing features beyond refactoring and hardening.

### References to read
- `user/client.py`, `user/internals/database.py`, `user/internals/auth0_validator.py`, `user/internals/auth0_service.py`, `user/models.py`, `user/schema.sql`, `user/exceptions.py`
- `api/endpoints/auth.py`, `api/endpoints/user.py`
- `shared/config.py`
- `scripts/init_workflow_db.py`
- Plans: `documentation/plans/2025-07-20-implement-auth0-with-coexistence.md`, `documentation/plans/2025-07-24-implement-user-balance-and-credit-system.md`, `documentation/plans/2025-07-23-implement-multi-user-support.md`

### Implementation plan (tasks)

1) Atomic balance deduction and clearer contract
- Update `user/internals/database.py` to deduct atomically using a conditional update: `UPDATE ... SET balance = balance - :cost WHERE uuid = :uuid AND balance >= :cost`.
- Update `user/client.py.deduct_from_balance` to raise `InsufficientBalanceError` when the DB update affects 0 rows (for Auth0 users), and return the updated user when it succeeds.
- Keep the existing guard that non‑Auth0 users are not charged.
- Add unit tests (new folder `user/tests/unit/`) covering:
  - Deduct succeeds when balance >= cost.
  - Deduct fails with `InsufficientBalanceError` when balance < cost.
  - Parallel deductions never drive balance negative.

2) Parameterize DB host via config
- In `user/internals/database.py`, stop hardcoding `host='db'`; instead use `settings.MYSQL_HOST` (fallback to `'db'` to keep existing behavior if needed).
- Ensure `shared/config.py` contains `MYSQL_HOST` and is loaded from env.
- Validate local dev and docker-compose scenarios still work.

3) Centralize password-mode auth helpers in `user` ✅
- Create `user/auth.py` (or `user/internals/password_auth.py`) that exposes pure functions used by password-mode auth in `api/endpoints/auth.py`:
  - `get_auth_configuration_status()`
  - `get_active_password()`
  - `get_session_token(password: str)`
  - `verify_session_token(token: str) -> bool`
  - `set_password(new_password: str)`
  - `login(password: str) -> session_token`
  - `get_auth_mode() -> Literal['auth0','password','none']`
- Move the email claim namespace used for Auth0 (`https://api.brewdock.com/email`) behind a constant or setting in `user/auth.py` (e.g. from `shared/config.py`).
- Refactor `api/endpoints/auth.py` to call into these helpers, keeping the endpoint layer a thin delegator.
  - Implemented `user/internals/password_auth.py` and exposed via `user/client.py`.
  - Updated `api/endpoints/auth.py` to call centralized helpers for mode, status, set-password, verify, and login.

4) Centralize admin checks ✅
- Add to `user/client.py`:
  - `is_admin(user: User) -> bool` (reads from `settings.ADMIN_USER_IDS`).
  - `add_admin_flag(user: User) -> User` to set `user.is_admin` consistently.
- Update `api/endpoints/user.py` to use these helpers in `is_admin` dependency and `/users/me` response enrichment.
  - Implemented `is_admin` and `add_admin_flag` in `user/client.py` and refactored the endpoint.

5) Align balance defaults across model and schema
- Decide on the canonical initial balance for Auth0 users (current behavior implies `$5.00`).
- Align `user/models.py` default for `User.balance` and `user/schema.sql` default to the same chosen value.
- Update `scripts/init_workflow_db.py` to avoid double-setting or conflicting backfills; only backfill when adding the column for the first time.

6) Clarify or remove unused Auth0 management helpers
- Review `user/internals/auth0_service.py`:
  - If account linking / management flows are planned soon, keep `get_auth0_management_client()` and document expected usage.
  - Remove or clearly comment `get_token_for_user()` if not applicable to our flow (Client Credentials cannot impersonate a user; avoid confusion).
- If kept, wire any used helpers through `user/client.py` so callers never import internals directly.

7) Public API improvements for `user` ✅ (partial)
- Expose a `create_user(user: User) -> User` thin wrapper in `user/client.py` to mirror the internal DB function.
- Update `user/__init__.py` to export the package’s public API (`client`, `models`, `exceptions`) for a cleaner import surface.
  - Added centralized helpers to resolve Auth0 users from token payloads via `user.client.find_or_create_user_from_auth0_payload` and `user.client.validate_auth0_token`, and refactored `api/endpoints/auth.py` accordingly.

8) Tests and guardrails
- Unit tests:
  - Balance deduction (see task 1).
  - Admin check and `add_admin_flag`.
  - Password-mode helpers (token generation/verification, set password, login flows) where feasible without I/O.
- Integration tests (fastapi):
  - `get_current_user` dependency in Auth0 mode (using a mock JWKS) and password mode.
  - `/users/{id}/balance` admin-only endpoint uses centralized logic.

9) Documentation updates
- Update `README.md`/developer docs to reflect:
  - New `MYSQL_HOST` setting.
  - Centralized password-mode helpers in `user` and endpoint changes.
  - The canonical default balance and how it’s enforced.
  - Public API of `user` package and where to add user-related features.

### Acceptance criteria
- All user responsibilities (auth helpers, admin checks, balance logic, user creation/discovery) live in `user` and are consumed by other layers.
- Atomic deduction cannot drive a balance negative; concurrent deductions behave correctly.
- No hardcoded DB host in `user/internals/database.py`.
- Password-mode logic in endpoints is a thin wrapper over `user` helpers.
- Admin logic is centralized and reused.
- Defaults for balance are consistent between model, schema, and init script.
- CI tests for user logic pass and cover the above.

### Rollout plan
- Implement tasks behind unit tests first.
- Apply DB/config changes; verify local and containerized environments.
- Refactor endpoints to use new helpers; run API integration tests.
- Verify workflows and prompt optimizer still function under both Auth0 and password modes.

### Risks and mitigations
- Balance logic regressions: mitigate with thorough unit tests and a staging environment.
- Auth regressions: use integration tests with mocked JWKS and password mode, verify cookie/session behavior.
- Environment parity: document `MYSQL_HOST` and provide defaults; validate docker-compose.

### Backout plan
- Revert the refactor commits.
- Restore previous deduction behavior and endpoint-local helpers if needed.



### Title: Implement Auth0 with Co-existence for Flexible Authentication

**Date:** 2025-07-20

**Status:** In Progress

---

### 1. Summary

This document outlines a plan to integrate Auth0 as a flexible, advanced authentication option while preserving the existing simple password-based and self-settable password authentication methods. The goal is to allow users to choose their preferred security model without forcing a migration or removing existing functionality. Auth0 will be enabled via environment variables and will act as a superseding layer when configured.

---

### 2. Guiding Principle: Configuration-Driven Authentication

The entire implementation will be governed by a master switch in the `.env` file.

*   **Master Switch**: The presence of the `AUTH0_DOMAIN` environment variable.
    *   If `AUTH0_DOMAIN` is set, Auth0 mode is **active**.
    *   If `AUTH0_DOMAIN` is **not** set, the system defaults to the **legacy password/self-settable password** modes.

This approach ensures backward compatibility and makes the new functionality strictly opt-in.

---

### 3. Key Requirement: Guest User Flow with Account Linking

To reduce user friction, we will support a "guest" user flow, allowing new users to create workflows *before* they officially sign up.

*   **Anonymous User Creation**: When a new, unauthenticated user arrives, the backend will use the Auth0 Management API to create an "anonymous" user profile (e.g., with a `<uuid>@guest.brewdock.com` identity). The application will issue a standard JWT for this anonymous user.
*   **Data Association**: All workflows and assets created by this user will be associated with their anonymous Auth0 user ID in our database.
*   **Account Linking on Signup**: When the user decides to sign up with a social provider (Google) or email/password, a second, permanent user profile is created by Auth0. Our backend will then use the Auth0 Management API to **link** the original anonymous account to this new primary account.
*   **Benefit**: This seamlessly merges the user's guest activity with their permanent account. No complex data migration is needed on our end; Auth0 handles the identity merge.

---

### 4. Security Considerations

*   **Secure Account Linking**: The `/auth/migrate` endpoint is critical for security. To ensure only the rightful owner can link an anonymous account, the frontend must pass the anonymous user's JWT in the request. The backend will validate both the newly authenticated user's session and the anonymous JWT before executing the link via the Auth0 Management API. This prevents session-hijacking or unauthorized account merging.

*   **Auth0 Management API Access**: The backend requires privileged access to manage users in Auth0. This will be achieved by configuring a **Machine to Machine (M2M)** application in the Auth0 dashboard. The backend will use the M2M client ID and secret to obtain an access token. The principle of least privilege will be applied by granting only the minimum required permissions: `read:users`, `create:users`, and `update:users`.

*   **Scoped JWTs for Anonymous Users**: JWTs issued to anonymous "guest" users will be short-lived and have a restricted scope. They will grant permission to create and manage workflow data but will not be authorized to access any sensitive, application-wide resources or other users' data.

---

### 5. Backend Implementation Plan

1.  **New `user` Module and Table: [COMPLETED]**
    *   To properly encapsulate all new user and authentication logic, a new top-level `user/` module will be created. It will follow the project's existing architectural patterns, containing sub-modules like `client.py` for its public interface and `internals/database.py` for data access logic.
    *   This module will be responsible for all logic related to Auth0, anonymous users, and interaction with the `users` table. Other parts of the application (e.g., API endpoints) will interact with this module exclusively through its `client`.
    *   **Client Interface (`user/client.py`):** The client will expose the following key functions:
        *   `create_anonymous_user() -> User`: Creates a guest user in Auth0 and a corresponding record in the local `users` table. Called by the anonymous login endpoint.
        *   `link_accounts(anonymous_user_sub: str, permanent_user_sub: str)`: Links the anonymous guest account to a newly created permanent account via the Auth0 Management API.
        *   `find_or_create_user_from_auth0(auth0_profile: dict) -> User`: Looks up a user by their `auth0_sub`. If not found, it creates a new record in the local database from the Auth0 profile. Used during the main login flow.
        *   `get_default_system_user() -> User`: Retrieves the single, shared user record for password-based authentication mode.
    *   **Note**: The existing legacy authentication logic in `api/endpoints/auth.py` will remain in place for now. The new `get_current_user` dependency will act as the integration point between the old and new systems.
    *   A central `users` table will be added to the primary database to unify the user model across all authentication methods.
    *   **Schema:**
        ```sql
        CREATE TABLE users (
            uuid BINARY(16) PRIMARY KEY,
            auth0_sub VARCHAR(255) UNIQUE, -- Populated in Auth0 mode. The Auth0 user ID.
            email VARCHAR(255) UNIQUE,
            is_anonymous BOOLEAN DEFAULT FALSE, -- Used for the guest -> registered flow in Auth0 mode.
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ```
    *   **Implementation**: The `CREATE TABLE` statement will be placed in a new `user/schema.sql` file. The `scripts/init_workflow_db.py` script will be updated to read and execute this new schema file during application startup, following the pattern used for the `workflow` and `prompt_optimizer` modules.

2.  **Default System User (for Password Mode): [COMPLETED]**
    *   On startup, **only if the system is in password-auth mode** (i.e., Auth0 is disabled but password variables are set), a script will ensure a single, default system user exists in the `users` table with a constant, well-known UUID.
    *   In "no auth" mode, this table will not be used, and the system will retain its original behavior of using a hardcoded user ID. This ensures that a database record is not required for the system to run without authentication.
    *   **Implementation**: The logic for conditionally creating this default user will be added to `scripts/init_workflow_db.py`. After initializing the schema, the script will check the relevant environment variables. If in password-auth mode, it will execute an idempotent `INSERT` (e.g., `INSERT IGNORE`) to create the default user record.

3.  **Conditional API Routing:**
    *   The main FastAPI router will conditionally mount endpoints based on the active authentication mode.
        ```python
        # In api/endpoints/auth.py
        from shared.config import settings

        if settings.AUTH0_DOMAIN:
            # Mount Auth0-specific endpoints:
            # POST /auth/anonymous-login
            # POST /auth/migrate
        else:
            # Mount legacy endpoints:
            # POST /auth/login
            # POST /auth/set-password
        ```

4.  **Unified User Dependency: [COMPLETED]**
    *   A single FastAPI dependency, `get_current_user`, will be implemented to resolve the user ID according to the three possible authentication states.
    *   **Logic:**
        *   If Auth0 is enabled, it will validate the incoming Auth0 JWT `Bearer` token and use the `user.client` to look up the user `uuid` from the `users` table via the `sub` claim.
        *   Else if Password auth is enabled, it will validate the legacy session cookie and, if valid, use the `user.client` to retrieve the `uuid` of the default system user.
        *   Else (No Auth mode), it will return the hardcoded legacy UUID (`12345678-1234-5678-9012-123456789012`) to preserve existing functionality.
    *   All other services will use this single dependency, making them agnostic to the underlying authentication method.

5.  **Public Configuration Endpoint: [COMPLETED]**
    *   A new, unauthenticated endpoint, `GET /api/auth/mode`, will be created.
    *   It will read the server's environment variables to determine the active authentication state and return one of three possible values: `{"mode": "auth0"}`, `{"mode": "password"}`, or `{"mode": "none"}`. This makes the backend the single source of truth.

---

### 6. User Data Synchronization Strategy

To maintain simplicity in the initial implementation, the system will adopt a "create-on-first-login" approach for data synchronization between the application's `users` table and Auth0.

*   **Strategy**: A user record (containing `uuid`, `auth0_sub`, and `email`) will be created in the local database only upon the user's first successful login via Auth0. Subsequent logins will only read this record. There will be no mechanism for real-time updates from Auth0.
*   **Rationale**: The primary identifier for all security and data association purposes will be the immutable `auth0_sub` claim from the JWT. The locally stored email is treated as a record of the user's email at the time of signup and is not critical for core functionality. This approach avoids the complexity of implementing webhook listeners (via Auth0 Actions) and handling potential sync failures.
*   **Future Enhancement**: If future application features, such as email notifications, require a consistently up-to-date email address, a more robust real-time synchronization mechanism can be implemented using Auth0 Actions as a follow-up task.

---

### 7. Frontend Implementation Plan

1.  **API-Driven Configuration:**
    *   To eliminate redundant environment variables and make the backend the single source of truth, the frontend will determine the authentication mode by calling the new public API endpoint: `GET /api/auth/mode`.
    *   This endpoint will return a simple JSON object, e.g., `{"mode": "auth0"}`.
    *   To avoid performance degradation, the result of this API call will be aggressively cached on the Next.js server (e.g., using Next.js's native `fetch` caching or `unstable_cache`). This allows both server components and middleware to access the setting without repeated network requests.

2.  **Conditional Middleware (`middleware.ts`):**
    *   The middleware will fetch the cached authentication mode and act as a dispatcher for all three states.
        ```typescript
        import { getAuthMode } from "@/lib/auth"; // Example utility

        export async function middleware(req) {
          const authMode = await getAuthMode(); // Returns 'auth0', 'password', or 'none'

          if (authMode === 'auth0') {
            // Defer to the Auth0 Next.js SDK's middleware for session management.
          } else if (authMode === 'password') {
            // Execute the existing password-based middleware logic.
          } else {
            // In "none" mode, no authentication is required. Allow all requests.
            return NextResponse.next();
          }
        }
        ```

3.  **Conditional UI Rendering:**
    *   A React Context provider or a similar state management solution will make the `authMode` available to client components, initialized from the cached server-side fetch.
    *   This will be used in `layout.tsx` to conditionally render the Auth0 `UserProvider` if `authMode === 'auth0'`.
    *   The `/login` page will use this state to conditionally render the Auth0 universal login buttons (`authMode === 'auth0'`) or the existing password form (`authMode === 'password'`). If `authMode === 'none'`, no login UI will be accessible.

---

### 8. User Experience (UX) Considerations

*   **Handling Lost Anonymous Sessions**: The anonymous guest flow relies on a JWT stored on the client. If a user clears their browser data or the token expires, the session and any associated work will be lost. The plan acknowledges this limitation. To mitigate this, the UI should proactively and non-intrusively prompt guest users to sign up to "save" their progress, especially after they create their first workflow.

*   **Proper Logout Flow**: Logging out of an SSO system requires invalidating both the local session and the centralized Auth0 session. The frontend implementation will ensure that the logout process redirects the user to the Auth0 logout endpoint. This prevents a scenario where a user logs out of the application but remains logged into their identity provider, which could pose a security risk on shared computers. The `@auth0/nextjs-auth0` SDK provides functionality for this.

---

### 9. Dependencies and Configuration

#### Libraries

*   **Backend (`requirements.txt`):**
    *   `auth0-python`
*   **Frontend (`package.json`):**
    *   `@auth0/nextjs-auth0`

#### Environment Variables

The following environment variables will be required to configure Auth0 integration.

*   **Backend (`.env`):**
    *   `AUTH0_DOMAIN`: The Auth0 domain. Acts as the master switch.
    *   `AUTH0_API_AUDIENCE`: The API identifier (audience) for validating JWTs.
    *   `AUTH0_ISSUER_URL`: The issuer URL for token validation.
    *   `AUTH0_M2M_CLIENT_ID`: Client ID for the backend M2M application.
    *   `AUTH0_M2M_CLIENT_SECRET`: Client secret for the backend M2M application.

*   **Frontend (`.env.local`):**
    *   `AUTH0_SECRET`: A long, secret string used to encrypt the session cookie.
    *   `AUTH0_BASE_URL`: The base URL of the application.
    *   `AUTH0_ISSUER_BASE_URL`: The Auth0 issuer URL.
    *   `AUTH0_CLIENT_ID`: Client ID for the Next.js frontend application.
    *   `AUTH0_CLIENT_SECRET`: Client secret for the Next.js frontend application.

---

### 10. Benefits of This Approach

*   **Preserves Functionality:** The simple and effective password-based system remains fully intact for users who prefer it.
*   **Clear Separation of Concerns:** Logic for each auth system is kept separate and is toggled by a single configuration flag.
*   **Unified & Improved Data Model:** Introduces a proper `users` table, fixing the "hardcoded user ID" problem and ensuring data integrity across all modes.
*   **Future-Proof:** Provides a clear path for users to adopt more advanced authentication and for the platform to support more identity features in the future. 
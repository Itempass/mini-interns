### Title: Implement Auth0 with Co-existence for Flexible Authentication

**Date:** 2025-07-20

**Status:** Proposed

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

### 4. Backend Implementation Plan

1.  **New `users` Table:**
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

2.  **Default System User (for Password Mode):**
    *   On startup, if Auth0 is disabled, a script will ensure a **single, default system user** exists in the `users` table with a constant, well-known UUID.
    *   This replaces all hardcoded user UUIDs in the current codebase and associates all data created in password-auth mode with this single entity.

3.  **Conditional API Routing:**
    *   The main FastAPI router will conditionally mount endpoints based on the active authentication mode.
        ```python
        # In api/endpoints/auth.py
        from shared.config import IS_AUTH0_ENABLED

        if IS_AUTH0_ENABLED:
            # Mount Auth0-specific endpoints:
            # POST /auth/anonymous-login
            # POST /auth/migrate
        else:
            # Mount legacy endpoints:
            # POST /auth/login
            # POST /auth/set-password
        ```

4.  **Unified User Dependency:**
    *   A single FastAPI dependency, `get_current_user`, will be implemented to resolve the user ID regardless of the auth mode.
    *   **Logic:**
        *   If Auth0 is enabled, it will validate the incoming Auth0 JWT `Bearer` token and look up the user `uuid` from the `users` table via the `sub` claim.
        *   If Auth0 is disabled, it will validate the legacy session cookie and, if valid, return the `uuid` of the default system user.
    *   All other services will use this dependency, making them agnostic to the auth method.

---

### 5. Frontend Implementation Plan

1.  **Environment-Based Dispatching:**
    *   A public environment variable, `NEXT_PUBLIC_AUTH_METHOD`, will be set to either `"auth0"` or `"password"` to control frontend logic.

2.  **Conditional Middleware (`middleware.ts`):**
    *   The middleware will act as a dispatcher.
        ```typescript
        if (process.env.NEXT_PUBLIC_AUTH_METHOD === 'auth0') {
          // Defer to the Auth0 Next.js SDK's middleware for session management.
        } else {
          // Execute the existing password-based middleware logic.
        }
        ```

3.  **Conditional UI Rendering:**
    *   The Auth0 `UserProvider` will only be rendered in `layout.tsx` if Auth0 is active.
    *   The `/login` page will conditionally render either the Auth0 universal login buttons or the existing password form.

---

### 6. Dependencies

*   **Backend (`requirements.txt`):**
    *   `auth0-python`
*   **Frontend (`package.json`):**
    *   `@auth0/nextjs-auth0`

---

### 7. Benefits of This Approach

*   **Preserves Functionality:** The simple and effective password-based system remains fully intact for users who prefer it.
*   **Clear Separation of Concerns:** Logic for each auth system is kept separate and is toggled by a single configuration flag.
*   **Unified & Improved Data Model:** Introduces a proper `users` table, fixing the "hardcoded user ID" problem and ensuring data integrity across all modes.
*   **Future-Proof:** Provides a clear path for users to adopt more advanced authentication and for the platform to support more identity features in the future. 
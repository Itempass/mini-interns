**Title:** Refactor: Improve IMAP Settings UX and Encrypt Credentials

**Summary:**

This pull request refactors the application's handling of IMAP settings to improve user experience and security. It introduces front-end enhancements for settings management and back-end encryption for sensitive credentials.

**Changes:**

*   **Feature: IMAP Connection Status Indicator**
    *   A `ConnectionStatusIndicator` component has been added to the main sidebar (`frontend/components/ConnectionStatusIndicator.tsx`).
    *   It periodically calls the `testImapConnection` API to provide real-time feedback on the IMAP connection status.

*   **Feature: Settings Page UX Enhancements**
    *   The settings page (`frontend/app/settings/page.tsx`) now visually indicates unsaved changes by controlling the state of the "Save" button.
    *   A help panel (`frontend/components/help/GoogleAppPasswordHelp.tsx`) has been added to guide users in generating a Google App Password.
    *   The "Test Connection" button is now disabled when there are unsaved settings to prevent user error.

*   **Feature: Encryption of Sensitive Data**
    *   A new encryption module (`shared/security/encryption.py`) using `cryptography.fernet` has been implemented to encrypt and decrypt sensitive application settings.
    *   The `save_app_settings` and `load_app_settings` functions in `shared/app_settings.py` now handle the encryption of `IMAP_PASSWORD` and `OPENROUTER_API_KEY`.
    *   A persistent encryption key is generated and stored in `/data/keys/secret.key`. `filelock` is used to manage concurrent access during key generation.

*   **Chore: Configuration and Dependency Updates**
    *   `Dockerfile` and `docker-compose.yaml` are updated to create and mount the `/data/keys` volume.
    *   Added `cryptography` and `filelock` to `requirements.txt`.
    *   Added `/data/keys/` to `.gitignore`. 
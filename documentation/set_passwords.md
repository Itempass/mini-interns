# Securing Your Brewdock Installation

By default, your Brewdock instance is accessible to anyone on your network. It is highly recommended to secure it with a password. There are two methods to do this, controlled by environment variables in your `.env` file.

---

### Method 1: Fixed Password (Recommended)

This method uses a single, fixed password that you set in your configuration files. It is the simplest and most direct way to secure your instance.

**How to configure:**

1.  Open your `.env` file, creating it from `.env.example` if it doesn't exist.
2.  Find the `AUTH_PASSWORD=` line.
3.  Add a secure password to it. For example:
    ```
    AUTH_PASSWORD=your_super_secret_password_123
    ```
4.  Restart your server.

Once set, all users will be prompted to enter this password before they can access the web interface. If this variable is left blank, this authentication method is disabled.

---

### Method 2: Self-settable Password

This method allows the first user who accesses a new installation to set the password through the web interface. This is useful for initial deployments where you want an end-user to define their own credentials without needing access to the `.env` file.

**How to configure:**

1.  Open your `.env` file.
2.  Find the `AUTH_SELFSET_PASSWORD=` line and set its value to `true`.
    ```
    AUTH_SELFSET_PASSWORD=true
    ```
3.  Restart your server.

**How it works:**

*   When this option is enabled, the first user to access the web interface will be greeted with a page to create a password.
*   Once set, this password will be required for all subsequent access.
*   The password file is stored securely at `data/keys/auth_password.key`. Ensure this path is included in your `.gitignore` file to prevent the password from being committed to version control.
*   This method takes priority over the `AUTH_PASSWORD` variable. If `AUTH_SELFSET_PASSWORD` is `true`, the system will ignore any value in `AUTH_PASSWORD`.

---

### Disabling Authentication

To disable password protection entirely, ensure both `AUTH_PASSWORD` is blank and `AUTH_SELFSET_PASSWORD` is `false` in your `.env` file. This is not recommended for instances exposed to a network. 
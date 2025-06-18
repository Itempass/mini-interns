# IMAP Email Poller

This script polls an IMAP inbox and creates a draft for each new email.

## Setup

1.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure for Gmail:**

    To use this script with Gmail, you need to use an **App Password**. Google no longer allows using your regular account password for third-party apps like this for security reasons.

    **A. Enable 2-Step Verification:**
    *   Go to your Google Account settings: [https://myaccount.google.com/](https://myaccount.google.com/)
    *   Navigate to the **Security** tab.
    *   Under "How you sign in to Google," click on **2-Step Verification** and enable it if you haven't already.

    **B. Generate an App Password:**
    *   On the same **Security** page, click on **App passwords**.
    *   When prompted, give the password a name (e.g., "IMAP Polling Script").
    *   Google will generate a 16-character password displayed in groups of 4. **Copy this password.**

    **C. Update the script:**
    *   Open `main.py`.
    *   Set `IMAP_USERNAME` to your full Gmail address (e.g., `"your_email@gmail.com"`).
    *   Set `IMAP_PASSWORD` to the 16-character App Password you just generated. **IMPORTANT: Paste it as a single string without any spaces.** (e.g., `"abcdabcdabcdabcd"`)

## Usage

To start polling your Gmail inbox, run the following command:

```bash
python main.py
```

## Troubleshooting

### `MailboxLoginError: [AUTHENTICATIONFAILED] Invalid credentials`

If you see this error, it means the script could not log in to your Gmail account. Here are the most common solutions:

1.  **Verify your App Password:**
    *   The most common cause is a typo in the password.
    *   Go back to your Google Account's [App passwords](https://myaccount.google.com/apppasswords) page.
    *   If you are unsure, it's best to **delete the existing App Password** and create a new one.
    *   Carefully copy the new 16-character password (without any spaces) and paste it into the `IMAP_PASSWORD` field in `main.py`.

2.  **Ensure IMAP is Enabled:**
    *   **For standard Gmail accounts (`@gmail.com`):**
        *   Go to your [Gmail settings](https://mail.google.com/mail/u/0/#settings/fwdandpop).
        *   Click the **Forwarding and POP/IMAP** tab.
        *   In the "IMAP access" section, make sure **Enable IMAP** is selected.
        *   Click **Save Changes** at the bottom of the page.
    *   **For Google Workspace accounts (your own domain):**
        *   As seen in your screenshot, if the "IMAP access" section is visible, **IMAP is already enabled**. You will not see a separate button to turn it on.
        *   If you've double-checked your App Password and still face issues, your Workspace administrator may have disabled access for third-party applications. You might need to check with them to ensure App Passwords are allowed for your organization.

3.  **Check for Security Alerts:**
    *   Check your Gmail inbox and spam folder for any "Security alert" emails from Google regarding a blocked sign-in attempt. If you find one, follow the instructions to verify the activity.

## How it works

The script connects to the specified IMAP server and checks for unseen emails in the inbox every 60 seconds. When a new email is found, it prints a message to the console indicating that a draft should be created.

**Note:** The actual logic for creating a draft is not implemented in this script, as it is highly dependent on the email provider's API (e.g., Gmail API, Microsoft Graph API). The script currently only contains a placeholder print statement. You will need to implement this part yourself based on your email provider's documentation. 
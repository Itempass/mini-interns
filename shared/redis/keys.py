from typing import List

class RedisKeys:
    """
    Centralized repository for Redis keys used throughout the application.
    """
    # Key for the last processed email UID
    @staticmethod
    def get_last_email_uid_key(username: str) -> str:
        """Returns the Redis key for storing the last email UID for a specific user."""
        if not username:
            # This case should ideally not be hit if checks are in place,
            # but it prevents a malformed key like "last_email_uid:"
            return "last_email_uid_default"
        return f"last_email_uid:{username}"

    # Key for inbox initialization status
    INBOX_INITIALIZATION_STATUS = "inbox:initialization:status"
    INBOX_VECTORIZATION_INTERRUPTED = "inbox:vectorization:interrupted"

    # Keys for application-wide settings
    IMAP_SERVER = "settings:imap_server"
    IMAP_USERNAME = "settings:imap_username"
    IMAP_PASSWORD = "settings:imap_password"
    EMBEDDING_MODEL = "settings:embedding_model"

    # --- Tone of Voice ---
    TONE_OF_VOICE_PROFILE = "tone_of_voice_profile"
    TONE_OF_VOICE_STATUS = "tone_of_voice_status"

    # Vectorization status keys
    INBOX_VECTORIZATION_STATUS = "inbox_vectorization_status" # e.g., 'running', 'completed', 'failed', 'not_started'
    INBOX_VECTORIZATION_LAST_ERROR = "inbox_vectorization_last_error"

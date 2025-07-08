from typing import List

class RedisKeys:
    """
    Centralized repository for Redis keys used throughout the application.
    """
    # Key for the last processed email UID
    LAST_EMAIL_UID = "last_email_uid"

    # Key for inbox initialization status
    INBOX_INITIALIZATION_STATUS = "inbox:initialization:status"
    INBOX_VECTORIZATION_INTERRUPTED = "inbox:vectorization:interrupted"

    # Keys for application-wide settings
    IMAP_SERVER = "settings:imap_server"
    IMAP_USERNAME = "settings:imap_username"
    IMAP_PASSWORD = "settings:imap_password"
    EMBEDDING_MODEL = "settings:embedding_model"

    # --- Vectorization ---
    VECTORIZATION_DATA_VERSION = "vectorization:data_version"

    # --- Tone of Voice ---
    TONE_OF_VOICE_PROFILE = "tone_of_voice_profile"
    TONE_OF_VOICE_STATUS = "tone_of_voice_status"

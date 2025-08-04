from typing import List
from uuid import UUID

class RedisKeys:
    """
    Centralized repository for Redis keys used throughout the application.
    This class uses methods to generate user-specific keys, ensuring data
    isolation in a multi-user environment.
    """
    # Key for the last processed email UID (User-Specific)
    @staticmethod
    def get_last_email_uid_key(user_uuid: UUID) -> str:
        """Returns the Redis key for storing the last email UID for a specific user."""
        return f"user:{user_uuid}:trigger:last_email_uid"

    # Key for inbox initialization status (User-Specific)
    @staticmethod
    def get_inbox_initialization_status_key(user_uuid: UUID) -> str:
        return f"user:{user_uuid}:inbox:initialization:status"

    # Key for vectorization interruption status (User-Specific)
    @staticmethod
    def get_inbox_vectorization_interrupted_key(user_uuid: UUID) -> str:
        return f"user:{user_uuid}:inbox:vectorization:interrupted"

    # Keys for application settings (User-Specific)
    @staticmethod
    def get_imap_server_key(user_uuid: UUID) -> str:
        return f"user:{user_uuid}:settings:imap_server"
    
    @staticmethod
    def get_imap_username_key(user_uuid: UUID) -> str:
        return f"user:{user_uuid}:settings:imap_username"

    @staticmethod
    def get_imap_password_key(user_uuid: UUID) -> str:
        return f"user:{user_uuid}:settings:imap_password"

    @staticmethod
    def get_embedding_model_key(user_uuid: UUID) -> str:
        return f"user:{user_uuid}:settings:embedding_model"

    # --- Vectorization (Global and User-Specific) ---
    VECTORIZATION_DATA_VERSION = "vectorization:data_version" # Global

    @staticmethod
    def get_vectorization_status_key(user_uuid: UUID) -> str: # User-Specific
        return f"user:{user_uuid}:inbox_vectorization_status"

    @staticmethod
    def get_vectorization_last_error_key(user_uuid: UUID) -> str: # User-Specific
        return f"user:{user_uuid}:inbox_vectorization_last_error"

    # --- Tone of Voice (User-Specific) ---
    @staticmethod
    def get_tone_of_voice_profile_key(user_uuid: UUID) -> str:
        return f"user:{user_uuid}:tone_of_voice_profile"

    @staticmethod
    def get_tone_of_voice_status_key(user_uuid: UUID) -> str:
        return f"user:{user_uuid}:tone_of_voice_status"

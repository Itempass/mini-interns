from typing import List

class RedisKeys:
    """
    Centralized repository for Redis keys used throughout the application.
    """
    # Key for the last processed email UID
    LAST_EMAIL_UID = "last_email_uid"

    # Key for inbox initialization status
    INBOX_INITIALIZATION_STATUS = "inbox:initialization:status"

    # Keys for application-wide settings
    IMAP_SERVER = "settings:imap_server"
    IMAP_USERNAME = "settings:imap_username"
    IMAP_PASSWORD = "settings:imap_password"
    OPENROUTER_API_KEY = "settings:openrouter_api_key"
    OPENROUTER_MODEL = "settings:openrouter_model"

    # Deprecated keys, kept for migration or cleanup
    AGENT_INSTRUCTIONS = "agent:agent_instructions"
    AGENT_TOOLS = "agent:tools"
    TRIGGER_CONDITIONS = "agent:trigger_conditions"
    FILTER_RULES = "agent:filter_rules"
    DEFAULT_AGENT_ID = "agent:default_agent_id"

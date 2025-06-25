from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
from typing import Optional

# Load environment variables from .env file.
# `override=True` ensures that the .env file takes precedence over system environment variables.
load_dotenv(override=True)

class Settings(BaseSettings):
    REDIS_URL: str
    AGENTLOGGER_ENABLE_ANONIMIZER: bool = True
    AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY: Optional[str] = None
    AGENTLOGGER_OPENROUTER_ANONIMIZER_MODEL: Optional[str] = None
    DISABLE_LOG_FORWARDING: bool = True
    CONTAINERPORT_MCP_IMAP: int
    CONTAINERPORT_API: int
    CONTAINERPORT_QDRANT: int
    EMBEDDING_VECTOR_SIZE: int
    EMBEDDING_MODEL_NAME: str
    EMBEDDING_OPENAI_API_KEY: Optional[str] = None
    QDRANT_NAMESPACE_UUID: str = 'a1b2c3d4-e5f6-7890-1234-567890abcdef' # For deterministic UUID generation for Qdrant points

    
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra='ignore')

settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from dotenv import load_dotenv
from typing import Optional, Any, Dict

# Load environment variables from .env file.
# `override=True` ensures that the .env file takes precedence over system environment variables.
load_dotenv(override=True)

class Settings(BaseSettings):
    REDIS_URL: str
    AGENTLOGGER_ENABLE_ANONIMIZER: bool = False
    AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY: Optional[str] = None
    AGENTLOGGER_OPENROUTER_ANONIMIZER_MODEL: Optional[str] = None
    DISABLE_LOG_FORWARDING: bool = True
    CONTAINERPORT_MCP_IMAP: int
    CONTAINERPORT_MCP_TONE_OF_VOICE: int
    CONTAINERPORT_API: int
    CONTAINERPORT_QDRANT: int
    CONTAINERPORT_QDRANT_GRPC: int
    EMBEDDING_OPENAI_API_KEY: Optional[str] = None
    EMBEDDING_VOYAGE_API_KEY: Optional[str] = None
    QDRANT_NAMESPACE_UUID: str = 'a1b2c3d4-e5f6-7890-1234-567890abcdef' # For deterministic UUID generation for Qdrant points
    OPENROUTER_API_KEY: str
    
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra='ignore')

settings = Settings()

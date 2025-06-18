from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load environment variables from .env file.
# `override=True` ensures that the .env file takes precedence over system environment variables.
load_dotenv(override=True)

class Settings(BaseSettings):
    REDIS_URL: str
  
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra='ignore')

settings = Settings()

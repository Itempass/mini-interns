import logging
import json
import redis
import sys
import os

# Add the project root to the Python path to allow for `shared` imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.config import settings
from typing import Dict, Any, Optional

# Configure logging to be consistent with other scripts
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_embedding_models() -> Dict[str, Any]:
    """
    Loads the embedding model definitions from the JSON file.
    """
    try:
        # The script runs from the /app directory in the container
        with open("shared/embedding_models.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("embedding_models.json not found.")
        return {}
    except json.JSONDecodeError:
        logging.error("Failed to decode embedding_models.json.")
        return {}

def find_best_available_model(models: Dict[str, Any]) -> Optional[str]:
    """
    Determines the best available embedding model based on defaults and available API keys.
    """
    provider_key_map = {
        "openai": settings.EMBEDDING_OPENAI_API_KEY,
        "voyage": settings.EMBEDDING_VOYAGE_API_KEY,
    }

    # First, try to find the model marked as default and check if its key is available
    for model_key, model_info in models.items():
        if model_info.get("default"):
            provider = model_info.get("provider")
            api_key = provider_key_map.get(provider)
            if provider and api_key and api_key != "EDIT-ME":
                logging.info(f"Default model '{model_key}' has its API key available. Selecting it.")
                return model_key
            else:
                logging.warning(f"Default model '{model_key}' is specified, but its API key is not available or is set to 'EDIT-ME'.")
                break  # Stop after checking the designated default

    # If the default model wasn't usable, find the first available model
    for model_key, model_info in models.items():
        provider = model_info.get("provider")
        api_key = provider_key_map.get(provider)
        if provider and api_key and api_key != "EDIT-ME":
            logging.info(f"Found first available model '{model_key}' with a configured API key.")
            return model_key

    logging.warning("No embedding models have a configured API key. Cannot set an initial model.")
    return None

def set_initial_embedding_model():
    """
    Sets the initial embedding model in Redis if it's not already set.
    """
    try:
        redis_client = get_redis_client()
        logging.info("Connected to Redis to set initial embedding model.")

        if redis_client.exists(RedisKeys.EMBEDDING_MODEL):
            current_model = redis_client.get(RedisKeys.EMBEDDING_MODEL)
            logging.info(f"Embedding model setting already exists in Redis (value: {current_model}). Skipping initialization.")
            return

        logging.info("Embedding model not set. Determining initial value...")
        models = get_embedding_models()
        if not models:
            return
            
        best_model_key = find_best_available_model(models)

        if best_model_key:
            redis_client.set(RedisKeys.EMBEDDING_MODEL, best_model_key)
            logging.info(f"Successfully set initial embedding model to '{best_model_key}'.")
        else:
            logging.info("No suitable initial embedding model found. Setting will remain unconfigured.")

    except redis.exceptions.ConnectionError as e:
        logging.error(f"Failed to connect to Redis: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while setting the initial embedding model: {e}", exc_info=True)

if __name__ == "__main__":
    set_initial_embedding_model() 
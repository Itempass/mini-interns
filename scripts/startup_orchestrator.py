import logging
import time
import httpx
import redis

# Set up paths and logger
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.config import VECTORIZATION_VERSION, settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RETRY_INTERVAL_S = 5
MAX_RETRIES = 12  # 60 seconds total

def wait_for_service(service_name: str, check_function, max_retries: int, retry_interval: int) -> bool:
    """
    Waits for a service to become available by repeatedly calling a check function.
    """
    logger.info(f"Waiting for {service_name} to become available...")
    for i in range(max_retries):
        try:
            if check_function():
                logger.info(f"{service_name} is available.")
                return True
        except Exception as e:
            logger.warning(f"Error connecting to {service_name}: {e}")
        
        logger.info(f"Retrying in {retry_interval}s... ({i+1}/{max_retries})")
        time.sleep(retry_interval)
    
    logger.error(f"Could not connect to {service_name} after {max_retries} retries. Aborting.")
    return False

def check_redis():
    """Checks if Redis is available by pinging it."""
    r = get_redis_client()
    r.ping()
    return True

def check_api():
    """Checks if the API is available by calling the /version endpoint."""
    api_url = f"http://localhost:{settings.CONTAINERPORT_API}/version"
    with httpx.Client() as client:
        response = client.get(api_url)
        response.raise_for_status()
    return True

def main():
    """
    Main orchestration logic.
    Waits for dependencies, checks vectorization version, and triggers
    re-vectorization if needed.
    """
    if not wait_for_service("Redis", check_redis, MAX_RETRIES, RETRY_INTERVAL_S):
        sys.exit(1)
        
    if not wait_for_service("API Server", check_api, MAX_RETRIES, RETRY_INTERVAL_S):
        sys.exit(1)

    redis_client = get_redis_client()
    
    try:
        # Before checking the version, ensure the app has been configured at least once.
        # If there's no IMAP server setting, it's a fresh install.
        if not redis_client.exists(RedisKeys.IMAP_SERVER):
            logger.info("IMAP settings not found. Assuming fresh install. Skipping vectorization check.")
            sys.exit(0)

        # The redis-py client decodes responses to utf-8 by default.
        data_version = redis_client.get(RedisKeys.VECTORIZATION_DATA_VERSION)
        
        logger.info(f"Code vectorization version: {VECTORIZATION_VERSION}")
        logger.info(f"Stored data vectorization version: {data_version}")

        if data_version != VECTORIZATION_VERSION:
            logger.info("Vectorization version mismatch. Triggering re-initialization.")
            
            reinitialize_url = f"http://localhost:{settings.CONTAINERPORT_API}/agent/reinitialize-inbox"
            try:
                with httpx.Client() as client:
                    # Using a timeout because the request will return immediately, but we want to be safe.
                    response = client.post(reinitialize_url, timeout=30.0)
                    response.raise_for_status()
                logger.info(f"Successfully triggered re-initialization: {response.json()}")
            except httpx.RequestError as e:
                logger.error(f"Failed to trigger re-initialization. Request error: {e}")
                sys.exit(1)
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to trigger re-initialization. Status code: {e.response.status_code}, Body: {e.response.text}")
                sys.exit(1)
        else:
            logger.info("Vectorization version is up-to-date. No action needed.")

    except redis.exceptions.RedisError as e:
        logger.error(f"An error occurred with Redis: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 
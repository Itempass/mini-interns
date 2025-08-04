import redis
import time
import logging
import sys

# Add the project root to the Python path
sys.path.append('.')

from shared.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def clear_redis_key_on_startup():
    """
    Connects to Redis and clears the specified key.
    Includes a retry mechanism in case the Redis server is not yet ready.
    """
    max_retries = 5
    retry_delay = 3  # seconds

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries}: Connecting to Redis to clear startup key...")
            client = redis.from_url(settings.REDIS_URL)
            
            # Ping to ensure connection is alive
            client.ping()
            
            # The pattern for user-specific inbox initialization status keys
            pattern = "user:*:inbox:initialization:status"
            logger.info(f"Successfully connected to Redis. Scanning for keys matching pattern: {pattern}")
            
            keys_to_delete = [key for key in client.scan_iter(match=pattern)]
            
            if keys_to_delete:
                logger.info(f"Found and deleting {len(keys_to_delete)} keys matching the pattern.")
                client.delete(*keys_to_delete)
            else:
                logger.info("No matching keys found to delete.")

            logger.info("Startup cleanup complete.")
            return

        except redis.exceptions.ConnectionError as e:
            logger.warning(f"Could not connect to Redis: {e}. Retrying in {retry_delay} seconds...")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logger.error("Failed to connect to Redis after multiple retries. Aborting cleanup.")
                sys.exit(1) # Exit with an error code
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            sys.exit(1) # Exit with an error code

if __name__ == "__main__":
    clear_redis_key_on_startup() 
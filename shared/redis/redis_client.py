import redis
import logging
from functools import lru_cache
from shared.config import settings

logger = logging.getLogger(__name__)

@lru_cache(maxsize=None)
def get_redis_client():
    """
    Returns a Redis client instance.
    The connection is cached using lru_cache to ensure only one connection pool is created.
    """
    try:
        logger.info(f"Connecting to Redis at {settings.REDIS_URL}")
        # The from_url method automatically handles connection pooling
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        # Ping the server to check the connection
        client.ping()
        logger.info("Successfully connected to Redis")
        return client
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Could not connect to Redis: {e}")
        raise

# Example usage (optional, for direct testing of this module)
if __name__ == "__main__":
    try:
        redis_client = get_redis_client()
        redis_client.set("mykey", "hello")
        value = redis_client.get("mykey")
        print(f"Set and got value from Redis: {value}")
        
        # To demonstrate the cache is working, call it again
        redis_client_2 = get_redis_client()
        print(f"Is it the same client? {redis_client is redis_client_2}")

    except Exception as e:
        print(f"An error occurred: {e}") 
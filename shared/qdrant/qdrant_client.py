import logging
from functools import lru_cache
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

@lru_cache(maxsize=None)
def get_qdrant_client():
    """
    Returns a Qdrant client instance.
    The connection is cached using lru_cache to ensure only one connection is created.
    """
    try:
        # The Qdrant client will be configured to connect to the 'qdrant' service
        # within the Docker network on its gRPC port.
        client = QdrantClient(host="qdrant", port=6333)
        logger.info("Successfully connected to Qdrant")
        return client
    except Exception as e:
        logger.error(f"Could not connect to Qdrant: {e}")
        raise

# Example usage (for direct testing of this module)
if __name__ == "__main__":
    try:
        qdrant_client = get_qdrant_client()
        
        # To demonstrate the cache is working, call it again
        qdrant_client_2 = get_qdrant_client()
        print(f"Is it the same client? {qdrant_client is qdrant_client_2}")

    except Exception as e:
        print(f"An error occurred: {e}")
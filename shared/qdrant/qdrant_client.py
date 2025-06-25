import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional
import httpx

from qdrant_client import QdrantClient, models
from qdrant_client.http.models import PointStruct
from shared.config import settings
from shared.services.embedding_service import get_embedding

logger = logging.getLogger(__name__)

# Global instances for Qdrant client with enhanced connection settings
qdrant_client = QdrantClient(
    host="qdrant", 
    port=settings.CONTAINERPORT_QDRANT,
    grpc_port=6334,
    prefer_grpc=True,  # Use gRPC for better performance and connection handling
    timeout=30,  # 30 second timeout to prevent hanging connections
    limits=httpx.Limits(
        max_connections=20,  # Connection pool size
        max_keepalive_connections=5  # Keep some connections alive for reuse
    )
)

def _ensure_collection_exists(client: QdrantClient, collection_name: str, vector_size: int):
    """Ensures a collection exists, creating it if necessary."""
    try:
        client.get_collection(collection_name=collection_name)
        logger.info(f"Collection '{collection_name}' already exists.")
    except Exception as e:
        # Check if it's a "not found" type error, in which case we should create the collection
        if "not found" in str(e).lower() or "doesn't exist" in str(e).lower():
            logger.info(f"Collection '{collection_name}' not found. Creating...")
            try:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
                )
                logger.info(f"Collection '{collection_name}' created.")
            except Exception as create_error:
                # If creation fails because collection already exists (race condition), that's fine
                if "already exists" in str(create_error).lower():
                    logger.info(f"Collection '{collection_name}' was created by another process.")
                else:
                    logger.error(f"Failed to create collection '{collection_name}': {create_error}")
                    raise
        else:
            logger.error(f"Unexpected error checking collection '{collection_name}': {e}")
            raise

def recreate_collection(client: QdrantClient, collection_name: str, vector_size: int):
    """Deletes and recreates a collection to ensure it's empty."""
    try:
        logger.warning(f"Deleting collection '{collection_name}'...")
        client.delete_collection(collection_name=collection_name)
        logger.info(f"Collection '{collection_name}' deleted.")
    except Exception as e:
        logger.info(f"Could not delete collection '{collection_name}' (it might not exist): {e}")
    
    _ensure_collection_exists(client, collection_name, vector_size)

@lru_cache(maxsize=None)
def get_qdrant_client():
    """
    Returns a cached Qdrant client instance and ensures the default 'emails' collection exists.
    """
    try:
        # The vector size is determined by the embedding model.
        vector_size = settings.EMBEDDING_VECTOR_SIZE 
        _ensure_collection_exists(qdrant_client, "emails", vector_size)
        _ensure_collection_exists(qdrant_client, "email_threads", vector_size)
        logger.info("Successfully connected to Qdrant and ensured collections exist.")
        return qdrant_client
    except Exception as e:
        logger.error(f"Could not connect to Qdrant: {e}")
        raise

def upsert_points(collection_name: str, points: List[models.PointStruct]):
    """
    Upserts a list of points into a Qdrant collection using built-in batch upload with retry logic.
    """
    client = get_qdrant_client()
    
    if not points:
        return

    try:
        # Use upload_points which has built-in retry logic and better batch handling
        client.upload_points(
            collection_name=collection_name,
            points=points,
            batch_size=len(points),  # Upload all points in one batch since we're already batching
            max_retries=3,  # Built-in retry logic
            wait=True,  # Wait for completion
            parallel=1  # Single thread to avoid overwhelming the server
        )
        logger.info(f"Upserted {len(points)} points to collection '{collection_name}'. Status: completed")
    except Exception as e:
        logger.error(f"Error upserting points to Qdrant collection '{collection_name}': {e}", exc_info=True)
        raise Exception("Failed to upsert points to Qdrant.") from e

def count_points(collection_name: str) -> int:
    """Counts the number of points in a Qdrant collection."""
    qdrant_client = get_qdrant_client()
    try:
        count_result = qdrant_client.count(
            collection_name=collection_name,
            exact=False
        )
        return count_result.count
    except Exception:
        # This can happen if the collection doesn't exist.
        return 0

def semantic_search(
    collection_name: str, query: str, top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Performs a semantic search in a Qdrant collection.
    """
    client = get_qdrant_client()
    
    query_vector = get_embedding(query)

    qdrant_filter = models.Filter()

    try:
        search_result = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        return [{"score": hit.score, **hit.payload} for hit in search_result]
    except Exception as e:
        logger.error(f"Error querying Qdrant: {e}")
        raise Exception("Failed to query Qdrant.") from e

def search_by_vector(
    collection_name: str,
    query_vector: List[float],
    top_k: int = 5,
    exclude_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Performs a vector search in a Qdrant collection, with an option to exclude specific point IDs.
    """
    client = get_qdrant_client()

    qdrant_filter = None
    if exclude_ids:
        qdrant_filter = models.Filter(
            must_not=[
                models.HasIdCondition(has_id=exclude_ids)
            ]
        )

    try:
        search_result = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        return [{"score": hit.score, **hit.payload} for hit in search_result]
    except Exception as e:
        logger.error(f"Error querying Qdrant with vector: {e}")
        raise Exception("Failed to query Qdrant by vector.") from e

# Initialize the client and collection on module load
get_qdrant_client()

# Example usage (for direct testing of this module)
if __name__ == "__main__":
    try:
        qdrant_client = get_qdrant_client()
        
        # To demonstrate the cache is working, call it again
        qdrant_client_2 = get_qdrant_client()
        print(f"Is it the same client? {qdrant_client is qdrant_client_2}")

    except Exception as e:
        print(f"An error occurred: {e}")
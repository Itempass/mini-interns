import logging
from functools import lru_cache
from typing import List, Dict, Any

from qdrant_client import QdrantClient, models
from fastembed.embedding import DefaultEmbedding

logger = logging.getLogger(__name__)

# Global instances for embedding model and Qdrant client
embedding_model = DefaultEmbedding()
qdrant_client = QdrantClient(host="qdrant", port=6333)

def _ensure_collection_exists(client: QdrantClient, collection_name: str, vector_size: int):
    """Ensures a collection exists, creating it if necessary."""
    try:
        client.get_collection(collection_name=collection_name)
    except Exception:
        logger.info(f"Collection '{collection_name}' not found. Creating...")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
        logger.info(f"Collection '{collection_name}' created.")

@lru_cache(maxsize=None)
def get_qdrant_client():
    """
    Returns a cached Qdrant client instance and ensures the default 'emails' collection exists.
    """
    try:
        # The vector size is determined by the embedding model.
        # For DefaultEmbedding ("BAAI/bge-small-en-v1.5"), the size is 384.
        vector_size = 384 
        _ensure_collection_exists(qdrant_client, "emails", vector_size)
        logger.info("Successfully connected to Qdrant and ensured 'emails' collection exists.")
        return qdrant_client
    except Exception as e:
        logger.error(f"Could not connect to Qdrant: {e}")
        raise

def semantic_search(
    collection_name: str, query: str, user_email: str, top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Performs a semantic search in a Qdrant collection.
    """
    client = get_qdrant_client()
    
    query_vector = list(embedding_model.embed(query))[0].tolist()

    qdrant_filter = models.Filter(
        must=[models.FieldCondition(key="user_email", match=models.MatchValue(value=user_email))]
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
        logger.error(f"Error querying Qdrant for user '{user_email}': {e}")
        raise Exception("Failed to query Qdrant.") from e

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
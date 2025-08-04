import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional
import httpx
import uuid
import numpy as np
from collections import Counter
from uuid import UUID

from qdrant_client import QdrantClient, models
from qdrant_client.http.models import PointStruct
from shared.config import settings
from shared.services.embedding_service import get_embedding, embedding_service

logger = logging.getLogger(__name__)

def generate_qdrant_point_id(identifier: str) -> str:
    """
    Generate a consistent Qdrant point ID from an identifier using UUID5.
    
    Args:
        identifier: The unique identifier (e.g., thread_id, message_id, etc.)
        
    Returns:
        A consistent UUID string that can be used as a Qdrant point ID
    """
    return str(uuid.uuid5(uuid.UUID(settings.QDRANT_NAMESPACE_UUID), identifier))

# Global instances for Qdrant client with enhanced connection settings
qdrant_client = QdrantClient(
    host="qdrant", 
    port=settings.CONTAINERPORT_QDRANT,
    grpc_port=settings.CONTAINERPORT_QDRANT_GRPC,
    prefer_grpc=True,  # Use gRPC for better performance and connection handling
    timeout=30,  # 30 second timeout to prevent hanging connections
    limits=httpx.Limits(
        max_connections=20,  # Connection pool size
        max_keepalive_connections=5  # Keep some connections alive for reuse
    )
)

def _get_user_collection_name(user_uuid: UUID) -> str:
    """Generates a Qdrant collection name for a user."""
    # Qdrant collection names must be valid RFC 1123 hostnames, so no underscores.
    return f"user-{str(user_uuid).replace('-', '')}"

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

def recreate_collection(user_uuid: UUID):
    """Deletes and recreates a user-specific collection to ensure it's empty."""
    client = get_qdrant_client()
    collection_name = _get_user_collection_name(user_uuid)
    vector_size = embedding_service.get_current_model_vector_size(user_uuid=user_uuid)
    try:
        logger.warning(f"Deleting collection '{collection_name}' for user {user_uuid}...")
        client.delete_collection(collection_name=collection_name)
        logger.info(f"Collection '{collection_name}' deleted.")
    except Exception as e:
        logger.info(f"Could not delete collection '{collection_name}' (it might not exist): {e}")
    
    _ensure_collection_exists(client, collection_name, vector_size)

def get_qdrant_client():
    """
    Returns a Qdrant client instance.
    """
    return qdrant_client

def upsert_points(points: List[models.PointStruct], user_uuid: UUID):
    """
    Upserts a list of points into a user-specific Qdrant collection.
    """
    client = get_qdrant_client()
    collection_name = _get_user_collection_name(user_uuid)
    
    if not points:
        return

    try:
        vector_size = embedding_service.get_current_model_vector_size(user_uuid=user_uuid)
        _ensure_collection_exists(client, collection_name, vector_size)
        
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

def count_points(user_uuid: UUID) -> int:
    """Counts the number of points in a user-specific Qdrant collection."""
    qdrant_client = get_qdrant_client()
    collection_name = _get_user_collection_name(user_uuid)
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
    query: str, user_uuid: UUID, top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Performs a semantic search in a user-specific Qdrant collection.
    """
    client = get_qdrant_client()
    collection_name = _get_user_collection_name(user_uuid)
    
    query_vector = get_embedding(query, user_uuid=user_uuid)

    qdrant_filter = models.Filter()

    try:
        vector_size = embedding_service.get_current_model_vector_size(user_uuid=user_uuid)
        _ensure_collection_exists(client, collection_name, vector_size)

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
    query_vector: List[float],
    user_uuid: UUID,
    top_k: int = 5,
    exclude_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Performs a vector search in a user-specific Qdrant collection, with an option to exclude specific point IDs.
    """
    client = get_qdrant_client()
    collection_name = _get_user_collection_name(user_uuid)

    qdrant_filter = None
    if exclude_ids:
        qdrant_filter = models.Filter(
            must_not=[
                models.HasIdCondition(has_id=exclude_ids)
            ]
        )

    try:
        vector_size = embedding_service.get_current_model_vector_size(user_uuid=user_uuid)
        _ensure_collection_exists(client, collection_name, vector_size)

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

def get_payload_field_distribution(field_name: str, user_uuid: UUID) -> Dict[str, int]:
    """
    Scans a user-specific collection and returns the distribution of values for a specific payload field.
    This is useful for getting counts of categorical data, like 'language'.
    """
    client = get_qdrant_client()
    collection_name = _get_user_collection_name(user_uuid)
    counter = Counter()
    next_offset = None  # Initialize offset for the first call

    try:
        vector_size = embedding_service.get_current_model_vector_size(user_uuid=user_uuid)
        _ensure_collection_exists(client, collection_name, vector_size)

        logger.info(f"Starting scroll to get distribution of '{field_name}' in '{collection_name}'...")
        while True:
            # Use the scroll method with the current offset
            points_batch, next_offset = client.scroll(
                collection_name=collection_name,
                limit=256,
                offset=next_offset,
                with_payload=[field_name],
                with_vectors=False,
            )

            # Process the points in the current batch
            for point in points_batch:
                field_value = point.payload.get(field_name)
                if field_value:
                    counter[field_value] += 1
            
            # If there's no next_offset, we've reached the end
            if not next_offset:
                break
        
        logger.info(f"Finished scroll. Found distribution: {counter}")
        return dict(counter)

    except Exception as e:
        logger.error(f"Error getting payload field distribution for '{field_name}' in '{collection_name}': {e}")
        return {}

def get_diverse_set_by_filter(
    query_filter: models.Filter, 
    user_uuid: UUID,
    limit: int = 10, 
    candidates: int = 100
) -> List[Dict[str, Any]]:
    """
    Selects a diverse set of documents from a user-specific collection that match a given filter.
    It uses a Maximal Marginal Relevance (MMR) like approach to ensure the selected
    documents are topically different from each other.
    """
    client = get_qdrant_client()
    collection_name = _get_user_collection_name(user_uuid)
    vector_size = embedding_service.get_current_model_vector_size(user_uuid=user_uuid)

    try:
        _ensure_collection_exists(client, collection_name, vector_size)
        # 1. Fetch a pool of candidate documents using a random vector to get a good starting sample
        random_vector = np.random.rand(vector_size).tolist()
        
        candidate_hits = client.search(
            collection_name=collection_name,
            query_vector=random_vector,
            query_filter=query_filter,
            limit=candidates,
            with_vectors=True,
            with_payload=True
        )

        if not candidate_hits:
            logger.warning(f"Could not find any candidates for filter in '{collection_name}'.")
            return []

        if len(candidate_hits) < limit:
            logger.warning(f"Found fewer candidates ({len(candidate_hits)}) than requested limit ({limit}). Returning all candidates.")
            return [hit.payload for hit in candidate_hits]

        # 2. Use a diversification algorithm (MMR-like) to select a diverse set
        candidate_vectors = np.array([hit.vector for hit in candidate_hits])
        
        # Normalize vectors for cosine similarity calculation
        candidate_vectors /= np.linalg.norm(candidate_vectors, axis=1, keepdims=True)

        selected_indices = []
        
        # Start with a random index from the candidates
        first_index = np.random.randint(len(candidate_hits))
        selected_indices.append(first_index)

        while len(selected_indices) < limit:
            last_selected_index = selected_indices[-1]
            last_selected_vector = candidate_vectors[last_selected_index]
            
            # Calculate cosine similarity of all candidates to the last selected one
            similarities = np.dot(candidate_vectors, last_selected_vector)

            # Find the candidate that is most dissimilar (min similarity) to the last one
            # and that has not already been selected.
            min_similarity = float('inf')
            next_index = -1
            
            for i in range(len(candidate_hits)):
                if i not in selected_indices:
                    if similarities[i] < min_similarity:
                        min_similarity = similarities[i]
                        next_index = i
            
            if next_index != -1:
                selected_indices.append(next_index)
            else:
                # This should not happen if there are enough candidates, but as a fallback
                break
        
        # 3. Return the payloads of the selected diverse hits
        diverse_payloads = [candidate_hits[i].payload for i in selected_indices]
        return diverse_payloads

    except Exception as e:
        logger.error(f"Error getting diverse set from '{collection_name}': {e}", exc_info=True)
        return []

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
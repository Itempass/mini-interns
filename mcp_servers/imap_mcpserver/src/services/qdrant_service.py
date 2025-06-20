import os
import logging
from typing import List, Dict, Any

from qdrant_client import models
from fastembed.embedding import DefaultEmbedding
from shared.qdrant.qdrant_client import get_qdrant_client

logger = logging.getLogger(__name__)

class QdrantService:
    """A service for interacting with the Qdrant vector database."""

    def __init__(self, collection_name: str = "emails"):
        """Initializes the QdrantService."""
        self.collection_name = collection_name
        self.embedding_model = DefaultEmbedding()
        self.client = get_qdrant_client()
        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        """Ensures that the specified collection exists in Qdrant, creating it if necessary."""
        try:
            self.client.get_collection(collection_name=self.collection_name)
            logger.info(f"[QdrantService] Collection '{self.collection_name}' already exists.")
        except Exception:
            logger.info(f"[QdrantService] Collection '{self.collection_name}' not found. Creating it...")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=384,  # Default for fastembed's DefaultEmbedding
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(f"[QdrantService] Collection '{self.collection_name}' created successfully.")

    def search(self, query: str, user_email: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Performs a semantic search in the Qdrant collection for a user's emails.

        Args:
            query: The natural language query string.
            user_email: The email of the user to filter results for.
            top_k: The number of top results to return.

        Returns:
            A list of matching email results from Qdrant.
        """
        if not user_email:
            raise ValueError("user_email must be provided for Qdrant query.")

        logger.debug(f"[QdrantService] Generating embedding for query: '{query[:50]}...'")
        query_vector = list(self.embedding_model.embed(query))[0].tolist()

        qdrant_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="user_email",
                    match=models.MatchValue(value=user_email),
                )
            ]
        )

        try:
            logger.debug(f"[QdrantService] Querying collection '{self.collection_name}' for user '{user_email}' with top_k={top_k}.")
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=top_k,
                with_payload=True,
            )
            
            if not search_result:
                logger.info(f"[QdrantService] No matches found for user '{user_email}'.")
                return []

            logger.info(f"[QdrantService] Found {len(search_result)} matches for user '{user_email}'.")
            
            formatted_results = [
                {
                    "score": hit.score,
                    **hit.payload,
                }
                for hit in search_result
            ]
            return formatted_results

        except Exception as e:
            logger.error(f"[QdrantService] Error querying Qdrant for user '{user_email}': {e}")
            raise Exception("Failed to query Qdrant.") from e
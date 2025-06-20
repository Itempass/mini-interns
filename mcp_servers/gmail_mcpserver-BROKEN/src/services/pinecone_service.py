"""
Service to handle interactions with the Pinecone vector database.
"""
import os
import logging
from typing import List, Dict, Any
from pinecone import Pinecone, PineconeException

from .embedding_service import EmbeddingService

# Set up logging
logger = logging.getLogger(__name__)

class PineconeService:
    """A service for querying a Pinecone index."""

    def __init__(self):
        """Initializes the PineconeService."""
        self.api_key = os.getenv("PINECONE_API_KEY")
        self.index_name = os.getenv("PINECONE_INDEX_NAME")

        if not self.api_key or not self.index_name:
            raise ValueError("PINECONE_API_KEY and PINECONE_INDEX_NAME environment variables must be set.")

        try:
            pc = Pinecone(api_key=self.api_key)
            self.index = pc.Index(self.index_name)
            logger.info(f"[PineconeService] Initialized and connected to index '{self.index_name}'.")
            # Log index stats to confirm connection
            stats = self.index.describe_index_stats()
            logger.info(f"[PineconeService] Index stats: {stats}")

        except PineconeException as e:
            logger.error(f"[PineconeService] Failed to initialize Pinecone: {e}")
            raise RuntimeError(f"Could not connect to Pinecone index '{self.index_name}'.") from e
        
        self.embedding_service = EmbeddingService()

    def query_user_emails(self, user_email: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Queries the Pinecone index for a user's emails.

        Args:
            user_email: The email of the user to filter results for.
            query: The natural language query string.
            top_k: The number of top results to return.

        Returns:
            A list of matching email results from Pinecone.
        """
        if not user_email:
            raise ValueError("user_email must be provided for Pinecone query.")

        logger.debug(f"[PineconeService] Generating embedding for query: '{query[:50]}...'")
        query_vector = self.embedding_service.create_embedding(query)

        pinecone_filter = {'user_email': user_email}
        
        try:
            logger.debug(f"[PineconeService] Querying index for user '{user_email}' with top_k={top_k}.")
            results = self.index.query(
                vector=query_vector,
                top_k=top_k,
                filter=pinecone_filter,
                include_metadata=True
            )
            
            if not results or not results['matches']:
                logger.info(f"[PineconeService] No matches found for user '{user_email}'.")
                return []

            logger.info(f"[PineconeService] Found {len(results['matches'])} matches for user '{user_email}'.")
            
            # Format and return the results
            formatted_results = []
            for match in results['matches']:
                formatted_results.append({
                    "score": match['score'],
                    **match.get('metadata', {})
                })
            return formatted_results

        except PineconeException as e:
            logger.error(f"[PineconeService] Error querying Pinecone for user '{user_email}': {e}")
            raise Exception("Failed to query Pinecone.") from e 
"""
Service to handle vector embedding generation using Voyage AI.
"""
import os
import logging
from typing import List
import voyageai

# Set up logging
logger = logging.getLogger(__name__)

class EmbeddingService:
    """A service to create embeddings using a Voyage AI model."""

    def __init__(self):
        """Initializes the EmbeddingService."""
        self.api_key = os.getenv("EMBEDDING_VOYAGE_API_KEY")
        self.embedding_model = os.getenv("EMBEDDING_VOYAGE_MODEL", "voyage-3.5")
        raw_vector_size = os.getenv("EMBEDDING_VECTOR_SIZE")
        
        if not self.api_key:
            raise ValueError("EMBEDDING_VOYAGE_API_KEY environment variable not set.")
        
        if not raw_vector_size:
            raise ValueError("EMBEDDING_VECTOR_SIZE environment variable not set.")
        
        self.embedding_vector_size = int(raw_vector_size)
        
        self.client = voyageai.Client(api_key=self.api_key)
        logger.info(f"[EmbeddingService] Initialized with model: {self.embedding_model}, vector size: {self.embedding_vector_size}")

    def create_embedding(self, text: str) -> List[float]:
        """
        Creates a vector embedding for the given text.

        Args:
            text: The text to embed.

        Returns:
            The vector embedding as a list of floats.
        
        Raises:
            Exception: If the embedding generation fails.
        """
        if not text or not isinstance(text, str):
            logger.error("[EmbeddingService] Invalid input: Text cannot be empty or non-string.")
            raise ValueError("Input text cannot be empty or non-string.")

        try:
            logger.debug(f"[EmbeddingService] Creating embedding for text: '{text[:50]}...'")
            # Use the lower-level API directly to support output_dimension
            response = voyageai.Embedding.create(
                input=[text],
                model=self.embedding_model,
                input_type="document",
                output_dimension=self.embedding_vector_size,
                api_key=self.api_key
            )
            embedding = response.data[0].embedding
            logger.debug(f"[EmbeddingService] Successfully created embedding of dimension {len(embedding)}.")
            return embedding
        except Exception as e:
            logger.error(f"[EmbeddingService] An unexpected error occurred during embedding creation: {e}")
            raise Exception(f"An unexpected error occurred while creating embedding: {e}") from e 
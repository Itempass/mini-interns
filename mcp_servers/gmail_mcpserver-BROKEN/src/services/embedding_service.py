"""
Service to handle vector embedding generation using OpenAI.
"""
import os
import logging
from typing import List
from openai import OpenAI, OpenAIError

# Set up logging
logger = logging.getLogger(__name__)

class EmbeddingService:
    """A service to create embeddings using an OpenAI model."""

    def __init__(self):
        """Initializes the EmbeddingService."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"[EmbeddingService] Initialized with model: {self.embedding_model}")

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
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            embedding = response.data[0].embedding
            logger.debug(f"[EmbeddingService] Successfully created embedding of dimension {len(embedding)}.")
            return embedding
        except OpenAIError as e:
            logger.error(f"[EmbeddingService] OpenAI API error during embedding creation: {e}")
            raise Exception(f"Failed to create embedding due to OpenAI API error: {e}") from e
        except Exception as e:
            logger.error(f"[EmbeddingService] An unexpected error occurred during embedding creation: {e}")
            raise Exception(f"An unexpected error occurred while creating embedding: {e}") from e 
import logging
from typing import List
from openai import OpenAI, OpenAIError
from shared.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    """A service to create embeddings using an OpenAI model."""

    def __init__(self):
        """Initializes the EmbeddingService."""
        self.api_key = settings.EMBEDDING_OPENAI_API_KEY
        self.embedding_model = settings.EMBEDDING_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("EMBEDDING_OPENAI_API_KEY is not configured in settings.")
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"EmbeddingService initialized with model: {self.embedding_model}")

    def create_embedding(self, text: str) -> List[float]:
        """
        Creates a vector embedding for a single text.
        """
        if not text or not isinstance(text, str):
            logger.error("Invalid input: Text cannot be empty or non-string.")
            raise ValueError("Input text cannot be empty or non-string.")

        try:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except OpenAIError as e:
            logger.error(f"OpenAI API error during embedding creation: {e}")
            raise Exception(f"Failed to create embedding due to OpenAI API error: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred during embedding creation: {e}")
            raise Exception(f"An unexpected error occurred while creating embedding: {e}") from e

    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Creates vector embeddings for a list of texts.
        """
        if not texts or not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
            logger.error("Invalid input: Input must be a list of non-empty strings.")
            raise ValueError("Input must be a list of non-empty strings.")

        try:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=texts
            )
            return [d.embedding for d in response.data]
        except OpenAIError as e:
            logger.error(f"OpenAI API error during embedding creation for a batch: {e}")
            raise Exception(f"Failed to create embeddings due to OpenAI API error: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred during batch embedding creation: {e}")
            raise Exception(f"An unexpected error occurred while creating embeddings: {e}") from e

# A single instance to be used across the application
embedding_service = EmbeddingService()

def get_embedding(text: str) -> List[float]:
    """Convenience function to get an embedding for a single text."""
    return embedding_service.create_embedding(text)

def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Convenience function to get embeddings for a list of texts."""
    return embedding_service.create_embeddings(texts)
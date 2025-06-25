import logging
from typing import List, Dict, Any
import voyageai
from shared.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    """A service to create embeddings using a Voyage AI model."""

    def __init__(self):
        """Initializes the EmbeddingService."""
        self.api_key = settings.EMBEDDING_VOYAGE_API_KEY
        self.embedding_model = settings.EMBEDDING_VOYAGE_MODEL
        
        if not self.api_key:
            raise ValueError("EMBEDDING_VOYAGE_API_KEY is not configured in settings.")
        
        self.client = voyageai.Client(api_key=self.api_key)
        logger.info(f"EmbeddingService initialized with model: {self.embedding_model}")

    def create_embedding(self, text: str) -> List[float]:
        """
        Creates a vector embedding for a single text.
        """
        if not text or not isinstance(text, str):
            logger.error("Invalid input: Text cannot be empty or non-string.")
            raise ValueError("Input text cannot be empty or non-string.")

        try:
            # Use the lower-level API directly to support output_dimension
            response = voyageai.Embedding.create(
                input=[text],
                model=self.embedding_model,
                input_type="document",
                output_dimension=settings.EMBEDDING_VECTOR_SIZE,
                api_key=self.api_key
            )
            return response.data[0].embedding
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
            # Use the lower-level API directly to support output_dimension
            response = voyageai.Embedding.create(
                input=texts,
                model=self.embedding_model,
                input_type="document",
                output_dimension=settings.EMBEDDING_VECTOR_SIZE,
                api_key=self.api_key
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"An unexpected error occurred during batch embedding creation: {e}")
            raise Exception(f"An unexpected error occurred while creating embeddings: {e}") from e

    def rerank(self, query: str, documents: List[str], top_k: int = None) -> List[Dict[str, Any]]:
        """
        Reranks a list of documents based on their relevance to a query using Voyage AI's rerank-2 model.
        
        Args:
            query: The query text to rank documents against
            documents: List of document texts to rerank
            top_k: Maximum number of results to return (optional)
            
        Returns:
            List of dictionaries containing reranked results with scores and indices
        """
        if not query or not isinstance(query, str):
            logger.error("Invalid query: Query cannot be empty or non-string.")
            raise ValueError("Query cannot be empty or non-string.")
            
        if not documents or not isinstance(documents, list) or not all(isinstance(d, str) for d in documents):
            logger.error("Invalid documents: Documents must be a list of non-empty strings.")
            raise ValueError("Documents must be a list of non-empty strings.")

        try:
            # Use the lower-level API directly to access reranking
            response = voyageai.Reranking.create(
                query=query,
                documents=documents,
                model="rerank-2",
                top_k=top_k,
                api_key=self.api_key
            )
            
            # Extract reranking results from response.data
            reranked_results = []
            for result in response.data:
                reranked_results.append({
                    "index": result.index,
                    "relevance_score": result.relevance_score,
                    "document": documents[result.index]  # Get document from original list using index
                })
            
            return reranked_results
        except Exception as e:
            logger.error(f"An unexpected error occurred during reranking: {e}")
            raise Exception(f"An unexpected error occurred while reranking: {e}") from e

# A single instance to be used across the application
embedding_service = EmbeddingService()

def get_embedding(text: str) -> List[float]:
    """Convenience function to get an embedding for a single text."""
    return embedding_service.create_embedding(text)

def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Convenience function to get embeddings for a list of texts."""
    return embedding_service.create_embeddings(texts)

def rerank_documents(query: str, documents: List[str], top_k: int = None) -> List[Dict[str, Any]]:
    """Convenience function to rerank documents."""
    return embedding_service.rerank(query, documents, top_k)
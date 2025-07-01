import logging
import json
from typing import List, Optional, Dict, Any
import voyageai
import openai
from functools import lru_cache

from shared.config import settings
from shared.app_settings import load_app_settings

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ["voyage", "openai"]

class EmbeddingService:
    """A service to create embeddings using various providers."""

    def __init__(self):
        """
        Initializes the EmbeddingService. The actual client is loaded lazily.
        """
        self.client = None
        self.provider = None
        self.model_name = None
        self.api_key = None
        self.initialized_model_key = None
        logger.info("EmbeddingService initialized. Client will be loaded/re-loaded on use if settings change.")

    def get_current_model_info(self) -> Dict[str, Any]:
        """
        Loads and returns the full info dictionary for the currently configured model.
        """
        embedding_model_key = load_app_settings().EMBEDDING_MODEL
        if not embedding_model_key:
            raise ValueError("Embedding model is not configured. Please set it on the settings page.")
        return self._get_model_info(embedding_model_key)

    def get_current_model_vector_size(self) -> int:
        """
        Returns the vector size of the currently configured embedding model.
        """
        model_info = self.get_current_model_info()
        return model_info["vector_size"]

    def _lazy_load_client(self):
        """
        Loads or reloads the embedding client if the configured model has changed.
        This ensures the service always uses the up-to-date settings.
        """
        current_model_key = load_app_settings().EMBEDDING_MODEL
        if not current_model_key:
            raise ValueError("Embedding model is not configured. Please set it on the settings page.")

        # If the client is already loaded, check if the model key has changed
        if self.client and self.initialized_model_key == current_model_key:
            return  # No change, so we can return

        logger.info(f"Configuration change detected or first use. Loading client for model '{current_model_key}'...")
        
        model_info = self._get_model_info(current_model_key)
        self.provider = model_info.get("provider")

        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")

        self.model_name = model_info.get("model_name")
        
        if self.provider == "voyage":
            self.api_key = settings.EMBEDDING_VOYAGE_API_KEY
            if not self.api_key:
                raise ValueError("Voyage API key is not configured.")
            # The client is not used for embedding with Voyage, but we initialize it for consistency
            self.client = voyageai.Client(api_key=self.api_key)
        elif self.provider == "openai":
            self.api_key = settings.EMBEDDING_OPENAI_API_KEY
            if not self.api_key:
                raise ValueError("OpenAI API key is not configured.")
            self.client = openai.OpenAI(api_key=self.api_key)
        
        # Store the model key that this client was initialized with
        self.initialized_model_key = current_model_key
            
        logger.info(f"Embedding client loaded for provider '{self.provider}' with model '{self.model_name}'")

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_model_info(model_key: str) -> Dict[str, Any]:
        """Loads embedding model details from the JSON file."""
        try:
            with open("shared/embedding_models.json", "r") as f:
                models = json.load(f)
            if model_key not in models:
                raise ValueError(f"Model '{model_key}' not found in embedding_models.json")
            return models[model_key]
        except FileNotFoundError:
            raise ValueError("embedding_models.json not found.")

    def create_embedding(self, text: str) -> List[float]:
        self._lazy_load_client()
        if not text or not isinstance(text, str):
            logger.error("Invalid input: Text cannot be empty or non-string.")
            raise ValueError("Input text cannot be empty or non-string.")

        try:
            model_vector_size = self.get_current_model_vector_size()
            
            if self.provider == "voyage":
                response = voyageai.Embedding.create(
                    input=[text], model=self.model_name, input_type="document",
                    output_dimension=model_vector_size, api_key=self.api_key
                )
                return response.data[0].embedding
            elif self.provider == "openai":
                response = self.client.embeddings.create(
                    input=[text], model=self.model_name,
                    dimensions=model_vector_size
                )
                return response.data[0].embedding
        except Exception as e:
            logger.error(f"An unexpected error occurred during embedding creation: {e}")
            raise Exception(f"An unexpected error occurred while creating embedding: {e}") from e

    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        self._lazy_load_client()
        if not texts or not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
            logger.error("Invalid input: Input must be a list of non-empty strings.")
            raise ValueError("Input must be a list of non-empty strings.")

        try:
            model_vector_size = self.get_current_model_vector_size()
            
            if self.provider == "voyage":
                response = voyageai.Embedding.create(
                    input=texts, model=self.model_name, input_type="document",
                    output_dimension=model_vector_size, api_key=self.api_key
                )
                return [data.embedding for data in response.data]
            elif self.provider == "openai":
                response = self.client.embeddings.create(
                    input=texts, model=self.model_name,
                    dimensions=model_vector_size
                )
                return [d.embedding for d in response.data]
        except Exception as e:
            logger.error(f"An unexpected error occurred during batch embedding creation: {e}")
            raise Exception(f"An unexpected error occurred while creating embeddings: {e}") from e

    def rerank(self, query: str, documents: List[str], top_k: int = None) -> List[Dict[str, Any]]:
        self._lazy_load_client()
        if self.provider != "voyage":
            logger.info(f"Reranking skipped for provider '{self.provider}'. Reranking is currently only supported for Voyage.")
            # If top_k is not specified, return all documents, otherwise return top_k
            num_to_return = top_k if top_k is not None else len(documents)
            # The calling function expects a list of dicts with at least an 'index' key.
            return [{"index": i} for i in range(min(len(documents), num_to_return))]

        if not query or not isinstance(query, str):
            logger.error("Invalid query: Query cannot be empty or non-string.")
            raise ValueError("Query cannot be empty or non-string.")
            
        if not documents or not isinstance(documents, list) or not all(isinstance(d, str) for d in documents):
            logger.error("Invalid documents: Documents must be a list of non-empty strings.")
            raise ValueError("Documents must be a list of non-empty strings.")

        try:
            response = voyageai.Reranking.create(
                query=query, documents=documents, model="rerank-2",
                top_k=top_k, api_key=self.api_key
            )
            
            reranked_results = []
            for result in response.data:
                reranked_results.append({
                    "index": result.index,
                    "relevance_score": result.relevance_score,
                    "document": documents[result.index]
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
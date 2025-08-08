import logging
import json
from typing import List, Optional, Dict, Any
import voyageai
import openai
from functools import lru_cache
from uuid import UUID

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

    def get_current_model_info(self, user_uuid: Optional[UUID] = None) -> Dict[str, Any]:
        """
        Loads and returns the full info dictionary for the currently configured model for a user.
        """
        embedding_model_key = load_app_settings(user_uuid=user_uuid).EMBEDDING_MODEL
        if not embedding_model_key:
            raise ValueError("Embedding model is not configured. Please set it on the settings page.")
        return self._get_model_info(embedding_model_key)

    def get_current_model_vector_size(self, user_uuid: Optional[UUID] = None) -> int:
        """
        Returns the vector size of the currently configured embedding model for a user.
        """
        model_info = self.get_current_model_info(user_uuid=user_uuid)
        return model_info["vector_size"]

    def _lazy_load_client(self, user_uuid: Optional[UUID] = None):
        """
        Loads or reloads the embedding client if the configured model for the user has changed.
        """
        current_model_key = load_app_settings(user_uuid=user_uuid).EMBEDDING_MODEL
        if not current_model_key:
            raise ValueError("Embedding model is not configured for this user.")

        # If the client is already loaded, check if the model key has changed
        if self.client and self.initialized_model_key == current_model_key:
            return  # No change, so we can return

        logger.info(f"Configuration change for user {user_uuid} or first use. Loading client for model '{current_model_key}'...")
        
        model_info = self._get_model_info(current_model_key)
        self.provider = model_info.get("provider")

        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")

        self.model_name = model_info.get("model_name")
        
        if self.provider == "voyage":
            self.api_key = settings.EMBEDDING_VOYAGE_API_KEY
            if not self.api_key or self.api_key == "EDIT-ME":
                raise ValueError("Voyage API key is not configured or is set to 'EDIT-ME'.")
            # The client is not used for embedding with Voyage, but we initialize it for consistency
            self.client = voyageai.Client(api_key=self.api_key)
        elif self.provider == "openai":
            self.api_key = settings.EMBEDDING_OPENAI_API_KEY
            if not self.api_key or self.api_key == "EDIT-ME":
                raise ValueError("OpenAI API key is not configured or is set to 'EDIT-ME'.")
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

    def create_embedding(self, text: str, user_uuid: Optional[UUID] = None) -> List[float]:
        self._lazy_load_client(user_uuid=user_uuid)
        if not text or not isinstance(text, str):
            logger.error("Invalid input: Text cannot be empty or non-string.")
            raise ValueError("Input text cannot be empty or non-string.")

        try:
            model_vector_size = self.get_current_model_vector_size(user_uuid=user_uuid)
            
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

    def create_embeddings(self, texts: List[str], user_uuid: Optional[UUID] = None) -> List[List[float]]:
        self._lazy_load_client(user_uuid=user_uuid)
        if not texts or not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
            logger.error("Invalid input: Input must be a list of non-empty strings.")
            raise ValueError("Input must be a list of non-empty strings.")

        try:
            model_vector_size = self.get_current_model_vector_size(user_uuid=user_uuid)
            
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

    def rerank(self, query: str, documents: List[str], top_k: int = None, user_uuid: Optional[UUID] = None) -> List[Dict[str, Any]]:
        self._lazy_load_client(user_uuid=user_uuid)
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

# --- Simple helper functions for options ---
@lru_cache(maxsize=1)
def _load_all_embedding_models() -> Dict[str, Any]:
    try:
        with open("shared/embedding_models.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError("embedding_models.json not found.")

def list_embedding_model_keys() -> List[str]:
    """Returns a simple list of available embedding model keys."""
    models = _load_all_embedding_models()
    return list(models.keys())

def get_embedding_model_vector_size(model_key: str) -> int:
    """Returns the vector size for a given embedding model key."""
    info = EmbeddingService._get_model_info(model_key)
    return int(info.get("vector_size"))

# --- Validation helpers ---
def get_provider_for_model(model_key: str) -> str:
    info = EmbeddingService._get_model_info(model_key)
    provider = info.get("provider")
    if not provider:
        raise ValueError(f"Provider not found for model '{model_key}'.")
    return provider

def has_api_key_for_provider(provider: str) -> bool:
    if provider == "voyage":
        return bool(settings.EMBEDDING_VOYAGE_API_KEY) and settings.EMBEDDING_VOYAGE_API_KEY != "EDIT-ME"
    if provider == "openai":
        return bool(settings.EMBEDDING_OPENAI_API_KEY) and settings.EMBEDDING_OPENAI_API_KEY != "EDIT-ME"
    return False

def validate_embedding_api_key_for_model(model_key: str) -> None:
    provider = get_provider_for_model(model_key)
    if not has_api_key_for_provider(provider):
        env_name = "EMBEDDING_VOYAGE_API_KEY" if provider == "voyage" else "EMBEDDING_OPENAI_API_KEY"
        raise ValueError(f"Missing API key for provider '{provider}'. Please set {env_name} in your environment.")


def get_embedding(text: str, user_uuid: Optional[UUID] = None) -> List[float]:
    """Convenience function to get an embedding for a single text for a specific user."""
    return embedding_service.create_embedding(text, user_uuid=user_uuid)

def get_embeddings(texts: List[str], user_uuid: Optional[UUID] = None) -> List[List[float]]:
    """Convenience function to get embeddings for a list of texts for a specific user."""
    return embedding_service.create_embeddings(texts, user_uuid=user_uuid)

def rerank_documents(query: str, documents: List[str], top_k: int = None, user_uuid: Optional[UUID] = None) -> List[Dict[str, Any]]:
    """Convenience function to rerank documents for a specific user."""
    return embedding_service.rerank(query, documents, top_k, user_uuid=user_uuid)

# --- Model-explicit embedding helpers (do not rely on user's current model) ---

def create_embedding_for_model(model_key: str, text: str) -> List[float]:
    """
    Creates a single embedding using the specified model key, independent of per-user settings.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Input text cannot be empty or non-string.")
    info = EmbeddingService._get_model_info(model_key)
    provider = info.get("provider")
    model_name = info.get("model_name")
    vector_size = int(info.get("vector_size"))

    if provider == "voyage":
        if not settings.EMBEDDING_VOYAGE_API_KEY or settings.EMBEDDING_VOYAGE_API_KEY == "EDIT-ME":
            raise ValueError("Voyage API key is not configured.")
        response = voyageai.Embedding.create(
            input=[text], model=model_name, input_type="document",
            output_dimension=vector_size, api_key=settings.EMBEDDING_VOYAGE_API_KEY
        )
        return response.data[0].embedding
    elif provider == "openai":
        if not settings.EMBEDDING_OPENAI_API_KEY or settings.EMBEDDING_OPENAI_API_KEY == "EDIT-ME":
            raise ValueError("OpenAI API key is not configured.")
        client = openai.OpenAI(api_key=settings.EMBEDDING_OPENAI_API_KEY)
        response = client.embeddings.create(
            input=[text], model=model_name, dimensions=vector_size
        )
        return response.data[0].embedding
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")


def create_embeddings_for_model(model_key: str, texts: List[str]) -> List[List[float]]:
    """
    Creates embeddings for multiple texts using the specified model key, independent of per-user settings.
    """
    if not texts or not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
        raise ValueError("Input must be a list of non-empty strings.")
    info = EmbeddingService._get_model_info(model_key)
    provider = info.get("provider")
    model_name = info.get("model_name")
    vector_size = int(info.get("vector_size"))

    if provider == "voyage":
        if not settings.EMBEDDING_VOYAGE_API_KEY or settings.EMBEDDING_VOYAGE_API_KEY == "EDIT-ME":
            raise ValueError("Voyage API key is not configured.")
        response = voyageai.Embedding.create(
            input=texts, model=model_name, input_type="document",
            output_dimension=vector_size, api_key=settings.EMBEDDING_VOYAGE_API_KEY
        )
        return [data.embedding for data in response.data]
    elif provider == "openai":
        if not settings.EMBEDDING_OPENAI_API_KEY or settings.EMBEDDING_OPENAI_API_KEY == "EDIT-ME":
            raise ValueError("OpenAI API key is not configured.")
        client = openai.OpenAI(api_key=settings.EMBEDDING_OPENAI_API_KEY)
        response = client.embeddings.create(
            input=texts, model=model_name, dimensions=vector_size
        )
        return [d.embedding for d in response.data]
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")
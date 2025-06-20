import pytest
import os
from src.services.embedding_service import EmbeddingService

# Get the expected dimension from the environment variable, default to 1536 for text-embedding-3-small
EXPECTED_DIMENSION = int(os.getenv("OPENAI_EMBEDDING_DIMENSION", 1536))

@pytest.mark.skipif(not os.getenv("EMBEDDING_OPENAI_API_KEY"), reason="EMBEDDING_OPENAI_API_KEY is not set, skipping live API test.")
def test_create_embedding_live():
    """
    Tests the EmbeddingService's create_embedding method with a live API call.
    """
    # 1. Initialize the service
    service = EmbeddingService()
    
    # 2. Define test input
    test_text = "This is a test sentence for embedding."
    
    # 3. Generate embedding
    embedding = service.create_embedding(test_text)
    
    # 4. Assertions
    assert isinstance(embedding, list), "Embedding should be a list."
    assert len(embedding) == EXPECTED_DIMENSION, f"Embedding dimension should be {EXPECTED_DIMENSION} for the model."
    assert all(isinstance(x, float) for x in embedding), "All elements in the embedding should be floats."
    
    # Test invalid input
    with pytest.raises(ValueError):
        service.create_embedding("") # Empty string
    
    with pytest.raises(ValueError):
        service.create_embedding(None) # None input 
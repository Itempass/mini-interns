import pytest
import os
import sys
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))

# This assumes tests are run from the project root.
# The .env files should be located there.
load_dotenv(override=True)

from shared.services.embedding_service import EmbeddingService

@pytest.fixture(scope="module")
def embedding_service():
    """Fixture to provide an instance of the EmbeddingService."""
    if not os.getenv("EMBEDDING_VOYAGE_API_KEY") or os.getenv("EMBEDDING_VOYAGE_API_KEY") == "EDIT-ME":
        pytest.skip("EMBEDDING_VOYAGE_API_KEY is not set, skipping integration test.")
    
    return EmbeddingService()

@pytest.mark.integration
def test_create_embedding_live_api_call(embedding_service: EmbeddingService):
    """
    Tests that the create_embedding method successfully returns an embedding
    of the correct dimension by making a live call to the Voyage AI API.
    """
    # Arrange
    test_text = "This is an integration test for Voyage AI."
    # The expected dimension is read from the service instance itself, which gets it from the model config
    expected_dimension = embedding_service.get_current_model_vector_size()

    # Act
    embedding = embedding_service.create_embedding(test_text)

    # Assert
    assert isinstance(embedding, list)
    assert len(embedding) == expected_dimension, f"Expected dimension {expected_dimension}, but got {len(embedding)}"
    assert all(isinstance(val, float) for val in embedding) 
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

# Make sure the app settings are loaded before the service
from shared.app_settings import load_app_settings, AppSettings
from shared.services.embedding_service import EmbeddingService, embedding_service

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the embedding_service singleton before each test to ensure isolation."""
    embedding_service.__init__()

@patch('shared.services.embedding_service.load_app_settings')
@patch('shared.services.embedding_service.voyageai')
@patch('shared.services.embedding_service.openai')
def test_service_switches_provider_on_setting_change(mock_openai, mock_voyage, mock_load_settings):
    """
    Tests that the EmbeddingService correctly switches its internal provider
    when the application settings are changed between calls.
    """
    # 1. First call: Configure and use Voyage
    mock_load_settings.return_value = AppSettings(EMBEDDING_MODEL='voyage-3.5')
    # Mock the API call to avoid actual network requests
    mock_voyage.Embedding.create.return_value = MagicMock(data=[MagicMock(embedding=[0.1])])
    
    embedding_service.create_embedding("test with voyage")

    # Assert that Voyage was used
    assert embedding_service.provider == 'voyage'
    mock_voyage.Client.assert_called_once()
    mock_openai.OpenAI.assert_not_called()

    # 2. Second call: Configure and use OpenAI
    mock_load_settings.return_value = AppSettings(EMBEDDING_MODEL='text-embedding-3-large')
    # Mock the API call
    mock_openai.OpenAI.return_value.embeddings.create.return_value = MagicMock(data=[MagicMock(embedding=[0.2])])

    embedding_service.create_embedding("test with openai")
    
    # Assert that OpenAI was used
    assert embedding_service.provider == 'openai'
    mock_openai.OpenAI.assert_called_once()
    # Check that Voyage client was not called again
    mock_voyage.Client.assert_called_once()

if __name__ == '__main__':
    pytest.main() 
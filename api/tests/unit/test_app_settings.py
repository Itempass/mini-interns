import sys
import os
from unittest.mock import MagicMock, patch
import json

# Add project root to the Python path to allow for correct module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Create a mock for the entire qdrant_client module to prevent it from running its connection logic on import.
# This is necessary because the connection is initiated at the module level.
mock_qdrant_module = MagicMock()
sys.modules['shared.qdrant.qdrant_client'] = mock_qdrant_module

import pytest
from fastapi.testclient import TestClient

# Now that the problematic module is mocked, we can safely import the app
from api.main import app
from shared.app_settings import AppSettings
from shared.redis.keys import RedisKeys
from api.endpoints.app_settings import get_embedding_models_with_key_status

@pytest.fixture
def client():
    return TestClient(app)

@pytest.mark.parametrize("old_username, new_username, should_reset_uid", [
    # Case 1: Username changes, should reset UID
    ("old@example.com", "new@example.com", True),
    # Case 2: Username is the same, should NOT reset UID
    ("user@example.com", "user@example.com", False),
    # Case 3: Initial setup (no old username), should NOT reset UID
    (None, "new@example.com", False),
])
def test_set_settings_resets_uid_only_on_username_change(client, old_username, new_username, should_reset_uid):
    """
    Verifies that changing the IMAP username resets the last processed email UID,
    and other changes do not. This is a unit test focusing on the endpoint's logic.
    """
    mock_redis_client = MagicMock()
    old_settings = AppSettings(IMAP_USERNAME=old_username)
    new_settings_payload = {"IMAP_USERNAME": new_username, "IMAP_PASSWORD": "new_password"}

    with patch('api.endpoints.app_settings.load_app_settings', return_value=old_settings), \
         patch('api.endpoints.app_settings.get_redis_client', return_value=mock_redis_client), \
         patch('api.endpoints.app_settings.save_app_settings'):
        
        response = client.post("/settings", json=new_settings_payload)

    assert response.status_code == 200
    if should_reset_uid:
        mock_redis_client.delete.assert_called_once_with(RedisKeys.LAST_EMAIL_UID)
    else:
        mock_redis_client.delete.assert_not_called()

def test_get_embedding_models_with_key_status():
    """
    Tests the logic for checking API key availability for embedding models.
    """
    mock_models = {
        "model-with-key": {"provider": "provider-with-key"},
        "model-without-key": {"provider": "provider-without-key"},
        "model-with-edit-me": {"provider": "provider-with-edit-me"},
    }

    class MockSettings:
        EMBEDDING_PROVIDER_WITH_KEY_API_KEY = "a-real-key"
        EMBEDDING_PROVIDER_WITHOUT_KEY_API_KEY = ""
        EMBEDDING_PROVIDER_WITH_EDIT_ME_API_KEY = "EDIT-ME"

    # Patch the open function to return our mock models
    with patch("builtins.open", MagicMock()) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(mock_models)
        
        # Patch the settings object
        with patch("api.endpoints.app_settings.settings") as mock_settings:
            # Mock the provider_key_map inside the function
            mock_settings.EMBEDDING_OPENAI_API_KEY = "a-real-key"
            mock_settings.EMBEDDING_VOYAGE_API_KEY = "EDIT-ME"

            # Re-create a simplified mock of the models for this test
            mock_models_for_test = {
                "openai-model": {"provider": "openai"},
                "voyage-model": {"provider": "voyage"},
            }
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(mock_models_for_test)

            result = get_embedding_models_with_key_status()

    result_map = {model["model_name_from_key"]: model["api_key_provided"] for model in result}
    
    assert result_map["openai-model"] is True
    assert result_map["voyage-model"] is False
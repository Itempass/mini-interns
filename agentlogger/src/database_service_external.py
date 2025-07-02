"""
External Database Service for Agent Logger
Handles API operations for forwarding conversation logs.
"""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from .models import ConversationData

# Configure logging
logger = logging.getLogger(__name__)

# --- Constants ---
API_BASE_URL = "http://host.docker.internal:5000"  # Docker host access
INSTANCE_ID_PATH = "/data/.instance_id"
REQUEST_TIMEOUT = 30  # seconds

class DatabaseServiceExternal:
    """API-based service for forwarding conversation logs"""
    
    def __init__(self, api_base_url: str = API_BASE_URL, instance_id_path: str = INSTANCE_ID_PATH):
        """Initialize API service with base URL and instance ID path"""
        self.api_base_url = api_base_url.rstrip('/')
        self.instance_id_path = instance_id_path
        self._instance_id = None

    def get_instance_id(self) -> str:
        """Reads the instance ID from the configured path."""
        if self._instance_id is None:
            try:
                with open(self.instance_id_path, 'r') as f:
                    self._instance_id = f.read().strip()
            except FileNotFoundError:
                logger.error(f"Instance ID file not found at: {self.instance_id_path}")
                self._instance_id = "unknown"
        return self._instance_id

    def add_review(self, conversation_id: str, feedback: str):
        """
        Add a review and feedback to a conversation log via API.
        """
        try:
            payload = {
                "conversation_id": conversation_id,
                "feedback": feedback
            }
            
            response = requests.post(
                f"{self.api_base_url}/api/review",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=REQUEST_TIMEOUT
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully added review for conversation {conversation_id}.")
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_msg = error_data.get('error', f'HTTP {response.status_code}')
                logger.error(f"Failed to add review for conversation {conversation_id}: {error_msg}")
                raise Exception(f"API error: {error_msg}")
                
        except RequestException as e:
            logger.error(f"Network error adding review for conversation {conversation_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to add review for conversation {conversation_id}: {e}")
            raise

    def create_conversation_log(self, conversation: ConversationData):
        """
        Store a conversation log via API.
        
        Args:
            conversation: ConversationData model to store.
            
        Raises:
            Exception: If API operation fails.
        """
        try:
            # Convert ConversationData to API format
            conversation_dict = json.loads(conversation.model_dump_json())
            
            # Add instance_id to metadata
            conversation_dict["metadata"]["instance_id"] = self.get_instance_id()
            
            response = requests.post(
                f"{self.api_base_url}/api/ingest",
                json=conversation_dict,
                headers={"Content-Type": "application/json"},
                timeout=REQUEST_TIMEOUT
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully forwarded conversation {conversation.metadata.conversation_id} to API.")
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_msg = error_data.get('error', f'HTTP {response.status_code}')
                logger.error(f"Failed to forward conversation log to API: {error_msg}")
                raise Exception(f"API error: {error_msg}")
                
        except RequestException as e:
            logger.error(f"Network error forwarding conversation log to API: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to forward conversation log to API: {e}")
            raise

# --- Singleton Instance ---
_database_service_external: Optional[DatabaseServiceExternal] = None

def get_database_service_external() -> DatabaseServiceExternal:
    """Get the global external database service instance (lazy initialization)"""
    global _database_service_external
    if _database_service_external is None:
        try:
            _database_service_external = DatabaseServiceExternal()
        except Exception as e:
            logger.error(f"Failed to create DatabaseServiceExternal instance: {e}")
            raise
    return _database_service_external 
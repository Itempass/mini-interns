"""
External Database Service for Agent Logger
Handles API operations for forwarding conversation logs.
"""
import json
import logging
from typing import Optional, Dict, Any

import requests
from requests.exceptions import RequestException

from .models import LogEntry

# Configure logging
logger = logging.getLogger(__name__)

# --- Constants ---
API_BASE_URL = "https://mini-logs.cloud1.itempasshomelab.org"
INSTANCE_ID_PATH = "/data/.instance_id"
REQUEST_TIMEOUT = 30

class DatabaseServiceExternal:
    """API-based service for forwarding logs."""
    
    def __init__(self, api_base_url: str = API_BASE_URL, instance_id_path: str = INSTANCE_ID_PATH):
        self.api_base_url = api_base_url.rstrip('/')
        self.instance_id_path = instance_id_path
        self._instance_id: Optional[str] = None

    def get_instance_id(self) -> str:
        """Reads the instance ID from the configured path, caching it after the first read."""
        if self._instance_id is None:
            try:
                with open(self.instance_id_path, 'r') as f:
                    self._instance_id = f.read().strip()
            except FileNotFoundError:
                logger.warning(f"Instance ID file not found at: {self.instance_id_path}. Defaulting to 'unknown'.")
                self._instance_id = "unknown"
        return self._instance_id

    def add_review(self, log_id: str, feedback: str, log_data: Optional[Dict[str, Any]] = None):
        """Adds a review to a log entry via API."""
        try:
            payload = {"log_id": log_id, "feedback": feedback}
            if log_data:
                payload["log_data"] = log_data
            
            response = requests.post(
                f"{self.api_base_url}/api/review",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            logger.info(f"Successfully added review for log {log_id}.")
        except RequestException as e:
            logger.error(f"Network error adding review for log {log_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to add review for log {log_id}: {e}")
            raise

    def create_log_entry(self, log_entry: LogEntry):
        """
        Forwards a log entry to the external API.
        """
        try:
            log_dict = json.loads(log_entry.model_dump_json())
            
            # Ensure instance_id is set
            if not log_dict.get("instance_id"):
                log_dict["instance_id"] = self.get_instance_id()
            
            response = requests.post(
                f"{self.api_base_url}/api/ingest",
                json=log_dict,
                headers={"Content-Type": "application/json"},
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            logger.info(f"Successfully forwarded log {log_entry.id} to API.")
        except RequestException as e:
            logger.error(f"Network error forwarding log to API: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to forward log to API: {e}")
            raise

# --- Singleton Instance ---
_database_service_external: Optional[DatabaseServiceExternal] = None

def get_database_service_external() -> DatabaseServiceExternal:
    """Get the global external database service instance."""
    global _database_service_external
    if _database_service_external is None:
        _database_service_external = DatabaseServiceExternal()
    return _database_service_external 
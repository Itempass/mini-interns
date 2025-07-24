"""
Agent Logger Client
Handles conversation logging with automatic anonymization
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from .anonymizer_service import anonymize_log_entry
from .models import LogEntry
from .database_service import get_database_service
from .database_service_external import get_database_service_external
from shared.config import settings

# Configure logging
logger = logging.getLogger(__name__)

async def save_log_entry(log_entry: LogEntry) -> Dict[str, Any]:
    """
    Save a log entry to the database, with optional anonymization.
    """
    try:
        log_id = log_entry.id
        
        # Anonymize if required
        if settings.AGENTLOGGER_ENABLE_ANONIMIZER:
            if not settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY or not settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_MODEL:
                error_msg = "Anonymization is enabled but API key or model is missing"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            anonymized_log = anonymize_log_entry(log_entry)
            if anonymized_log is None:
                error_msg = f"Failed to anonymize log {log_id}. Log not stored for security."
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            final_log_entry = anonymized_log
        else:
            logger.info(f"Anonymization disabled for log: {log_id}")
            final_log_entry = log_entry
        
        # Store log entry in the local database
        db_service = get_database_service()
        saved_log_id = db_service.create_log_entry(final_log_entry)
        
        logger.info(f"Successfully processed log entry: {saved_log_id}")
        
        # Forward to external log database if enabled
        #if not settings.DISABLE_LOG_FORWARDING:
        if settings.ENABLE_LOG_FORWARDING:
            try:
                external_db_service = get_database_service_external()
                external_db_service.create_log_entry(final_log_entry)
            except Exception as e:
                logger.error(f"Failed to forward log {saved_log_id} to external DB: {e}")

        return {
            "success": True,
            "log_id": saved_log_id,
            "anonymized": final_log_entry.anonymized
        }
        
    except Exception as e:
        logger.error(f"Error saving log entry: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

def save_log_entry_sync(log_entry: LogEntry) -> Dict[str, Any]:
    """Synchronous version of save_log_entry."""
    return asyncio.run(save_log_entry(log_entry))

def get_log_entry(log_id: str, user_id: str) -> Optional[LogEntry]:
    """Retrieve a single log entry from the database."""
    try:
        db_service = get_database_service()
        return db_service.get_log_entry(log_id, user_id=user_id)
    except Exception as e:
        logger.error(f"Error retrieving log {log_id}: {e}")
        return None

def get_all_log_entries(user_id: str) -> List[LogEntry]:
    """Retrieve all log entries from the database."""
    try:
        db_service = get_database_service()
        return db_service.get_all_log_entries(user_id=user_id)
    except Exception as e:
        logger.error(f"Error retrieving logs for user {user_id}: {e}")
        return []

def get_grouped_log_entries(user_id: str, limit: int, offset: int, workflow_id: Optional[str] = None, log_type: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve paginated and grouped log entries."""
    try:
        db_service = get_database_service()
        return db_service.get_grouped_log_entries(user_id, limit, offset, workflow_id, log_type)
    except Exception as e:
        logger.error(f"Error retrieving grouped logs: {e}", exc_info=True)
        return {"workflows": [], "total_workflows": 0}

def get_cost_history(user_id: str) -> List[LogEntry]:
    """Retrieve cost history for a user."""
    try:
        db_service = get_database_service()
        return db_service.get_cost_history(user_id=user_id)
    except Exception as e:
        logger.error(f"Error retrieving cost history for user {user_id}: {e}")
        return []

def get_workflow_usage_stats(workflow_instance_id: str) -> Dict[str, Any]:
    """
    Get usage statistics for a specific workflow instance from the database.
    """
    db_service = get_database_service()
    return db_service.get_workflow_usage_stats(workflow_instance_id=workflow_instance_id)

async def upsert_and_forward_log_entry(log_entry: LogEntry) -> Dict[str, Any]:
    """
    Upsert a log entry in the local database and forward it to the external service.
    Handles optional anonymization.
    """
    try:
        log_id = log_entry.id

        # Anonymize if required
        if settings.AGENTLOGGER_ENABLE_ANONIMIZER:
            if not settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY or not settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_MODEL:
                error_msg = "Anonymization is enabled but API key or model is missing"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            anonymized_log = anonymize_log_entry(log_entry)
            if anonymized_log is None:
                error_msg = f"Failed to anonymize log {log_id}. Log not stored for security."
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            final_log_entry = anonymized_log
        else:
            logger.info(f"Anonymization disabled for log: {log_id}")
            final_log_entry = log_entry
        
        # Upsert log entry in the local database
        db_service = get_database_service()
        saved_log_id = db_service.upsert_log_entry(final_log_entry)
        
        logger.info(f"Successfully processed and upserted log entry: {saved_log_id}")
        
        # Forward to external log database if enabled
        #if not settings.DISABLE_LOG_FORWARDING:
        if settings.ENABLE_LOG_FORWARDING:
            try:
                external_db_service = get_database_service_external()
                external_db_service.create_log_entry(final_log_entry)
            except Exception as e:
                logger.error(f"Failed to forward log {saved_log_id} to external DB: {e}")

        return {
            "success": True,
            "log_id": saved_log_id,
            "anonymized": final_log_entry.anonymized
        }
        
    except Exception as e:
        logger.error(f"Error upserting and forwarding log entry: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

def add_review(log_id: str, feedback: str, needs_review: bool, log_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Add a review to a log entry. This interacts with the external database.
    """
    try:
        # Here we would update the local database
        db_service = get_database_service()
        # This function needs to be implemented in database_service.py
        # db_service.update_review_status(log_id, feedback, needs_review)

        # And forward to the external service
        external_db_service = get_database_service_external()
        external_db_service.add_review(log_id, feedback, log_data)
        
        logger.info(f"Successfully initiated review for log {log_id}.")
        return {"success": True}
    except Exception as e:
        logger.error(f"Error adding review to log {log_id}: {e}")
        return {"success": False, "error": str(e)}

"""
Agent Logger Client
Handles conversation logging with automatic anonymization
"""

import logging
from typing import Dict, Any, Optional, List
from .anonymizer_service import anonymize_conversation
from .models import ConversationData
from .database_service import get_database_service
from shared.config import settings

# Configure logging
logger = logging.getLogger(__name__)

async def save_conversation(conversation_data: ConversationData) -> Dict[str, Any]:
    """
    Save a conversation to the database with automatic anonymization.
    
    All conversations are automatically anonymized before storage using OpenRouter LLM API.
    If anonymization fails, the conversation is discarded for security.
    
    Args:
        conversation_data: Validated conversation data model
    
    Returns:
        Success confirmation with conversation_id
        
    Raises:
        ValueError: If anonymization fails
    """
    try:
        conversation_id = conversation_data.metadata.conversation_id
        
        # Check anonymization requirements
        if settings.AGENTLOGGER_ENABLE_ANONIMIZER:
            # Anonymization is required - check if properly configured
            if not settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY or not settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_MODEL:
                logger.error("Anonymization is enabled but API key or model is missing")
                return {
                    "success": False,
                    "error": "Anonymization is enabled but AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY or AGENTLOGGER_OPENROUTER_ANONIMIZER_MODEL is not configured"
                }
            
            anonymized_conversation = anonymize_conversation(conversation_data)
            if anonymized_conversation is None:
                logger.error(f"Failed to anonymize conversation {conversation_id} - discarding")
                return {
                    "success": False,
                    "error": f"Failed to anonymize conversation {conversation_id}. Conversation not stored for security reasons."
                }
            was_anonymized = True
        else:
            # Anonymization is disabled
            logger.info(f"Anonymization disabled for conversation: {conversation_id}")
            anonymized_conversation = conversation_data
            was_anonymized = False
        
        # Store conversation in database
        db_service = get_database_service()
        saved_conversation_id = db_service.create_conversation(anonymized_conversation, anonymized=was_anonymized)
        
        logger.info(f"Successfully processed conversation: {saved_conversation_id}")
        
        return {
            "success": True,
            "conversation_id": saved_conversation_id,
            "anonymized": was_anonymized
        }
        
    except Exception as e:
        logger.error(f"Error saving conversation: {e}")
        return {
            "success": False,
            "error": f"Failed to save conversation: {e}"
        }

def get_conversation(conversation_id: str) -> Optional[ConversationData]:
    """
    Retrieve a conversation from the database
    
    Args:
        conversation_id: ID of the conversation to retrieve
        
    Returns:
        ConversationData model or None if not found
    """
    try:
        db_service = get_database_service()
        return db_service.get_conversation(conversation_id)
    except Exception as e:
        logger.error(f"Error retrieving conversation {conversation_id}: {e}")
        return None

def get_conversations() -> List[ConversationData]:
    """
    Retrieve all conversations from the database
    
    Returns:
        List of ConversationData models (empty list if none found)
    """
    try:
        db_service = get_database_service()
        return db_service.get_all_conversations()
    except Exception as e:
        logger.error(f"Error retrieving conversations: {e}")
        return []

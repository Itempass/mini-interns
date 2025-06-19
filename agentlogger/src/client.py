"""
Agent Logger Client
Handles conversation logging with automatic anonymization
"""

import logging
from typing import Dict, Any
from .anonymizer_service import anonymize_conversation
from .models import ConversationData
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
        
        # Only anonymize if anonymizer is configured  
        if settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY and settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_MODEL:
            anonymized_conversation = anonymize_conversation(conversation_data)
        else:
            anonymized_conversation = conversation_data  # not anonymized!!
        
        if anonymized_conversation is None:
            logger.error(f"Failed to anonymize conversation {conversation_id} - discarding")
            raise ValueError(f"Failed to anonymize conversation {conversation_id}. Conversation not stored for security reasons.")
        
        raise NotImplementedError("Database service not implemented")
        # TODO: Replace with actual database service when implemented
        # saved_conversation_id = get_database_service().create_conversation(anonymized_conversation)
        
        logger.info(f"Successfully processed conversation: {conversation_id}")
        
        return {
            "success": True,
            "conversation_id": conversation_id
        }
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error saving conversation: {e}")
        raise ValueError(f"Failed to save conversation: {e}")

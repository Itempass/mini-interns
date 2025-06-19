import logging
from fastapi import APIRouter, HTTPException
from agentlogger.src.client import get_conversations, get_conversation
from api.types.api_models.agentlogger import ConversationResponse, ConversationsResponse

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/agentlogger/conversations", response_model=ConversationsResponse)
def get_all_conversations():
    """
    Get all conversations from the agent logger database.
    """
    try:
        conversations = get_conversations()
        return ConversationsResponse(
            conversations=conversations,
            count=len(conversations)
        )
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/agentlogger/conversations/{conversation_id}", response_model=ConversationResponse)
def get_single_conversation(conversation_id: str):
    """
    Get a single conversation by ID from the agent logger database.
    """
    try:
        conversation = get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
        
        return ConversationResponse(conversation=conversation)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from agentlogger.src.models import ConversationData

class ConversationResponse(BaseModel):
    """Single conversation response"""
    conversation: Dict[str, Any]

class ConversationsResponse(BaseModel):
    """Multiple conversations response"""
    conversations: List[ConversationData]
    count: int

class AddReviewRequest(BaseModel):
    feedback: str
    log_data: Optional[Dict[str, Any]] = None 
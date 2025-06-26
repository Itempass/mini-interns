from pydantic import BaseModel
from typing import List
from agentlogger.src.models import ConversationData

class ConversationResponse(BaseModel):
    """Single conversation response"""
    conversation: ConversationData

class ConversationsResponse(BaseModel):
    """Multiple conversations response"""
    conversations: List[ConversationData]
    count: int

class AddReviewRequest(BaseModel):
    feedback: str 
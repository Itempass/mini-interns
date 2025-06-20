"""
Data models for Agent Logger
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import datetime

class Message(BaseModel):
    """Individual message in a conversation"""
    content: Optional[str] = None
    role: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    # Allow additional fields for flexibility
    model_config = {"extra": "allow"}

class Metadata(BaseModel):
    """Conversation metadata"""
    conversation_id: str
    timestamp: Optional[str] = None
    # Allow additional metadata fields
    model_config = {"extra": "allow"}

class ConversationData(BaseModel):
    """Complete conversation data structure"""
    metadata: Metadata
    messages: List[Message] = Field(min_length=1, description="Must contain at least one message")
    
    # Allow additional top-level fields
    model_config = {"extra": "allow"}

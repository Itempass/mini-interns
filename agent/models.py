from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from typing import List, Optional, Dict, Any
from datetime import datetime

class Agent(BaseModel):
    uuid: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    system_prompt: str
    user_instructions: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Message(BaseModel):
    """Individual message in a conversation"""
    content: Optional[str] = None
    role: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    # Allow additional fields for flexibility
    model_config = {"extra": "allow"}

class AgentInstance(BaseModel):
    uuid: UUID = Field(default_factory=uuid4)
    agent_uuid: UUID
    user_input: str
    messages: List[Message] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

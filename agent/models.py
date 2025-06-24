from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from typing import List, Optional, Dict, Any
from datetime import datetime

class AgentModel(BaseModel):
    uuid: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    system_prompt: str
    user_instructions: str
    tools: Dict[str, Any] = Field(default_factory=dict) # tool_id -> { enabled: bool, required: bool, order: int }
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class MessageModel(BaseModel):
    """Individual message in a conversation"""
    content: Optional[str] = None
    role: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    # Allow additional fields for flexibility
    model_config = {"extra": "allow"}

class AgentInstanceModel(BaseModel):
    uuid: UUID = Field(default_factory=uuid4)
    agent_uuid: UUID
    user_input: str
    context_identifier: Optional[str] = None
    messages: List[MessageModel] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class TriggerModel(BaseModel):
    uuid: UUID = Field(default_factory=uuid4)
    agent_uuid: UUID
    trigger_conditions: str
    filter_rules: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

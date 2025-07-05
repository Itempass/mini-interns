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
    paused: bool = False
    model: str = Field(default="google/gemini-2.5-flash-preview-05-20:thinking")
    param_schema: List[Dict[str, Any]] = Field(default_factory=list)
    param_values: Dict[str, Any] = Field(default_factory=dict)
    use_abstracted_editor: bool = False
    template_id: Optional[str] = None
    template_version: Optional[str] = None
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
    trigger_bypass: bool = False # If True, the trigger will immediately be bypassed and the agent will run
    filter_rules: Dict[str, Any] = Field(default_factory=dict)
    model: str = Field(default="google/gemini-2.5-flash-preview-05-20:thinking")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

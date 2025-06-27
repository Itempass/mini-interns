from pydantic import BaseModel, Field
from uuid import UUID
from typing import Dict, Any
from datetime import datetime
from api.types.api_models.agent import FilterRules

class AgentWithTriggerSettings(BaseModel):
    uuid: UUID
    name: str
    description: str
    system_prompt: str
    user_instructions: str
    tools: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    trigger_conditions: str
    filter_rules: FilterRules

class CreateAgentRequest(BaseModel):
    name: str
    description: str
    user_instructions: str = ""
    trigger_conditions: str = ""
    filter_rules: FilterRules = Field(default_factory=FilterRules) 
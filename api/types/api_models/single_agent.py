from pydantic import BaseModel, Field
from uuid import UUID
from typing import Dict, Any, Optional, List
from datetime import datetime
from api.types.api_models.agent import FilterRules

class AgentWithTriggerSettings(BaseModel):
    uuid: UUID
    name: str
    description: str
    system_prompt: str
    user_instructions: str
    tools: Dict[str, Any] = Field(default_factory=dict)
    paused: bool = False
    model: str
    param_schema: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    param_values: Optional[Dict[str, Any]] = Field(default_factory=dict)
    use_abstracted_editor: bool = False
    created_at: datetime
    updated_at: datetime
    template_id: Optional[str] = None
    template_version: Optional[str] = None
    trigger_conditions: str
    filter_rules: FilterRules
    trigger_bypass: bool = False
    trigger_model: str

class CreateAgentRequest(BaseModel):
    name: str
    description: str
    user_instructions: str = ""
    model: Optional[str] = None
    trigger_conditions: str = ""
    filter_rules: FilterRules = Field(default_factory=FilterRules)
    trigger_model: Optional[str] = None

class AgentImportModel(BaseModel):
    name: str
    description: str
    system_prompt: str
    user_instructions: str
    tools: Dict[str, Any] = Field(default_factory=dict)
    paused: bool = False
    model: str
    param_schema: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    param_values: Optional[Dict[str, Any]] = Field(default_factory=dict)
    use_abstracted_editor: bool = False
    template_id: Optional[str] = None
    template_version: Optional[str] = None
    trigger_conditions: str
    filter_rules: FilterRules
    trigger_bypass: bool = False
    trigger_model: str

class TemplateInfo(BaseModel):
    id: str
    name: str
    description: str

class CreateFromTemplateRequest(BaseModel):
    template_id: str 
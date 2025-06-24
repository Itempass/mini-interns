from pydantic import BaseModel, Field
from typing import Optional, List

class FilterRules(BaseModel):
    """
    Pydantic model for filter rules.
    """
    email_blacklist: List[str] = Field(default_factory=list)
    email_whitelist: List[str] = Field(default_factory=list)
    domain_blacklist: List[str] = Field(default_factory=list)
    domain_whitelist: List[str] = Field(default_factory=list)

class AgentSettings(BaseModel):
    """
    A Pydantic model for agent settings.
    """
    #system_prompt: Optional[str] = None
    trigger_conditions: str | None = None
    #user_context: Optional[str] = None
    filter_rules: FilterRules | None = None
    #agent_steps: Optional[str] = None
    agent_instructions: str | None = None
    agent_tools: dict | None = None 
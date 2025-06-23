from pydantic import BaseModel
from typing import Optional, List

class FilterRules(BaseModel):
    """
    Pydantic model for filter rules.
    """
    email_blacklist: Optional[List[str]] = []
    email_whitelist: Optional[List[str]] = []
    domain_blacklist: Optional[List[str]] = []
    domain_whitelist: Optional[List[str]] = []

class AgentSettings(BaseModel):
    """
    A Pydantic model for agent settings.
    """
    #system_prompt: Optional[str] = None
    trigger_conditions: Optional[str] = None
    #user_context: Optional[str] = None
    filter_rules: Optional[FilterRules] = None
    #agent_steps: Optional[str] = None
    agent_instructions: Optional[str] = None 
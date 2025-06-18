from pydantic import BaseModel
from typing import Optional

class AgentSettings(BaseModel):
    """
    A Pydantic model for agent settings.
    """
    system_prompt: Optional[str] = None
    trigger_conditions: Optional[str] = None
    user_context: Optional[str] = None 
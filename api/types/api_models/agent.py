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

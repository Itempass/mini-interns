from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

class CreateVectorDatabaseRequest(BaseModel):
    name: str
    type: Literal["internal", "external"]
    provider: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    status: Optional[str] = None
    error_message: Optional[str] = None 
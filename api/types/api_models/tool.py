from pydantic import BaseModel
from typing import Dict, Any

class Tool(BaseModel):
    id: str
    name: str
    description: str
    server: str
    input_schema: Dict[str, Any] 
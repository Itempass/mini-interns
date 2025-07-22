from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: Optional[List[dict]] = None
    tool_call_id: Optional[str] = None

class HumanInputData(BaseModel):
    tool_call_id: str
    user_input: Dict[str, Any]

class ChatRequest(BaseModel):
    conversation_id: str
    messages: List[ChatMessage]
    human_input: Optional[HumanInputData] = None

class HumanInputRequired(BaseModel):
    type: str
    tool_call_id: str
    data: Dict[str, Any]

class ChatStepResponse(BaseModel):
    conversation_id: str
    messages: List[ChatMessage]
    is_complete: bool
    human_input_required: Optional[HumanInputRequired] = None 
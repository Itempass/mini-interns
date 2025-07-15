from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: Optional[List[dict]] = None
    tool_call_id: Optional[str] = None

class ChatRequest(BaseModel):
    conversation_id: str
    messages: List[ChatMessage]

class ChatStepResponse(BaseModel):
    conversation_id: str
    messages: List[ChatMessage]
    is_complete: bool 
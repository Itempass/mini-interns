from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class VectorDatabase(BaseModel):
    """Represents a configured vector database."""

    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = Field(..., description="A user-friendly name for the vector database configuration.")
    type: Literal["internal", "external"]
    provider: str = Field(..., description="The specific provider, e.g., 'pinecone', 'imap_email_threads'.")
    settings: Dict[str, Any] = Field(default_factory=dict)
    status: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) 
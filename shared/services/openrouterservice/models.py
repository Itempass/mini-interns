from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LLMCallResult(BaseModel):
    """Standard return object for all LLM calls.

    This model is intentionally complete so downstream systems (agentlogger,
    usage history, UI) can consume costs, usage, identifiers, and payloads
    without needing to re-parse raw provider responses.
    """

    # Identity and correlation
    uuid: UUID = Field(..., description="Application-wide, per-call unique ID")
    user_id: Optional[UUID] = Field(
        default=None, description="User responsible for the call"
    )
    model: str = Field(..., description="Model identifier used for the call")
    provider: Literal["openrouter"] = Field(
        default="openrouter", description="LLM provider name"
    )
    generation_id: Optional[str] = Field(
        default=None, description="Provider's generation ID (e.g., OpenRouter id)"
    )
    step_name: Optional[str] = Field(default=None, description="Optional step label")
    workflow_uuid: Optional[UUID] = Field(
        default=None, description="Workflow definition identifier"
    )
    workflow_instance_uuid: Optional[UUID] = Field(
        default=None, description="Workflow instance identifier"
    )

    # Timing
    start_time: datetime = Field(
        default_factory=datetime.utcnow, description="UTC timestamp when call started"
    )
    end_time: Optional[datetime] = Field(
        default=None, description="UTC timestamp when call finished"
    )

    # Metering and cost
    prompt_tokens: Optional[int] = Field(default=None)
    completion_tokens: Optional[int] = Field(default=None)
    total_tokens: Optional[int] = Field(default=None)
    total_cost: Optional[float] = Field(default=None, description="USD cost of call")
    currency: Literal["USD"] = Field(default="USD")

    # Payloads
    response_text: Optional[str] = Field(
        default=None, description="Convenience: first message content if present"
    )
    response_message: Optional[Dict[str, Any]] = Field(
        default=None, description="Structured message (tools, content, etc.)"
    )
    raw_response: Optional[Dict[str, Any]] = Field(
        default=None, description="Full raw provider response"
    )



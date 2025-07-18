"""
Data models for Agent Logger
"""
from __future__ import annotations
import datetime
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
import uuid

LogType = Literal['workflow', 'custom_agent', 'custom_llm', 'workflow_agent']

class Message(BaseModel):
    """Individual message in a conversation"""
    content: Optional[str] = None
    role: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    # Allow additional fields for flexibility
    model_config = {"extra": "allow"}

class LogEntry(BaseModel):
    """A single log entry for a workflow, step, or agent interaction."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    reference_string: Optional[str] = None
    log_type: LogType
    workflow_id: Optional[str] = None
    workflow_instance_id: Optional[str] = None
    workflow_name: Optional[str] = None
    step_id: Optional[str] = None
    step_instance_id: Optional[str] = None
    step_name: Optional[str] = None
    messages: Optional[List[Message]] = None
    needs_review: Optional[bool] = False
    feedback: Optional[str] = None
    start_time: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    end_time: Optional[datetime.datetime] = None
    anonymized: bool = False

    model_config = {"extra": "allow"}

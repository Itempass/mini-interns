from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class AddReviewRequest(BaseModel):
    feedback: str
    needs_review: bool
    log_data: Optional[Dict[str, Any]] = None

class LogEntryResponse(BaseModel):
    log_entry: Dict[str, Any]

class LogEntriesResponse(BaseModel):
    log_entries: List[Dict[str, Any]]
    count: int

class GroupedLog(BaseModel):
    workflow_log: Dict[str, Any]
    step_logs: List[Dict[str, Any]]

class GroupedLogEntriesResponse(BaseModel):
    workflows: List[GroupedLog]
    total_workflows: int

class WorkflowUsageStatsResponse(BaseModel):
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost: float 
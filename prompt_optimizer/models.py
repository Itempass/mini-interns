from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# --- Configuration Models ---

class DataSourceConfig(BaseModel):
    """Defines the source of data for an evaluation."""
    tool: str = Field(..., description="The name of the tool to call to fetch data, e.g., 'imap.get_emails'.")
    params: Dict[str, Any] = Field(default_factory=dict, description="The parameters to pass to the data fetching tool.")


class FieldMappingConfig(BaseModel):
    """Defines how to map fields from the fetched data to evaluation roles."""
    input_field: str = Field(..., description="The key in a single data item to be used as the input for the LLM prompt.")
    ground_truth_field: str = Field(..., description="The key in a single data item to be used as the ground truth for comparison.")
    ground_truth_transform: Optional[str] = None


# --- Database / Core Models ---

class EvaluationTemplate(BaseModel):
    """
    Represents a self-contained, static benchmark for evaluating a prompt.
    It contains the configuration for fetching data and a snapshot of that data.
    """
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str
    description: Optional[str] = None
    data_source_config: DataSourceConfig
    field_mapping_config: FieldMappingConfig
    cached_data: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "processing"
    processing_error: Optional[str] = None

class EvaluationTemplateLight(BaseModel):
    """A lightweight version of EvaluationTemplate for list views, excluding heavy data."""
    uuid: UUID
    user_id: UUID
    name: str
    description: Optional[str] = None
    updated_at: datetime


class TestCaseResult(BaseModel):
    """Represents the outcome of a single test case within an evaluation run."""
    input_data: Any
    ground_truth_data: Any
    generated_output: Any
    is_match: bool
    comparison_details: Optional[Dict[str, Any]] = None


class EvaluationRun(BaseModel):
    """Represents a single execution of an EvaluationTemplate against a prompt."""
    uuid: UUID = Field(default_factory=uuid4)
    user_id: UUID
    template_uuid: UUID
    original_prompt: str
    original_model: str
    status: Literal["pending", "running", "completed", "failed"]
    summary_report: Optional[Dict[str, Any]] = None
    detailed_results: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- API Request / Response Models ---

class EvaluationTemplateCreate(BaseModel):
    """Request model for creating a new EvaluationTemplate."""
    name: str
    description: Optional[str] = None
    data_source_config: DataSourceConfig
    field_mapping_config: FieldMappingConfig

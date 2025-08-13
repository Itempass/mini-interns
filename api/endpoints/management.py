import logging
import re
import json
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.responses import JSONResponse

import workflow.client as workflow_client
from workflow.models import WorkflowModel, WorkflowWithDetails
from api.types.api_models.agentlogger import (
    GroupedLogEntriesResponse,
    LogEntryResponse,
    CostHistoryResponse,
    CostLogEntry,
)
from agentlogger.src.client import (
    get_grouped_log_entries,
    get_log_entry,
    get_cost_history,
)

from api.endpoints.auth import get_current_user
from api.endpoints.user import is_admin


logger = logging.getLogger(__name__)

# All routes require authenticated admin. Read-only.
router = APIRouter(
    prefix="/management",
    tags=["management"],
    dependencies=[Depends(get_current_user), Depends(is_admin)],
)


@router.get("/users/{user_uuid}/workflows", response_model=List[WorkflowModel])
async def list_user_workflows(user_uuid: UUID) -> List[WorkflowModel]:
    """List all workflows for the specified user (admin view)."""
    return await workflow_client.list_all(user_id=user_uuid)


@router.get("/users/{user_uuid}/workflows/{workflow_uuid}", response_model=WorkflowWithDetails)
async def get_user_workflow_with_details(user_uuid: UUID, workflow_uuid: UUID) -> WorkflowWithDetails:
    """Get a single workflow with details for the specified user (admin view)."""
    workflow = await workflow_client.get_with_details(workflow_uuid=workflow_uuid, user_id=user_uuid)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


@router.get("/users/{user_uuid}/workflows/{workflow_uuid}/export")
async def export_user_workflow(user_uuid: UUID, workflow_uuid: UUID):
    """Export the specified user's workflow as JSON (admin view)."""
    workflow = await workflow_client.get_with_details(workflow_uuid=workflow_uuid, user_id=user_uuid)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    # Sanitize the workflow name to create a valid filename (match standard export behavior)
    sanitized_name = re.sub(r'[^\w\s-]', '_', workflow.name)
    safe_filename = re.sub(r'\s+', '_', sanitized_name).strip('_') or f"workflow_{workflow_uuid}"

    workflow_json = workflow.model_dump_json(indent=2)
    return JSONResponse(
        content=json.loads(workflow_json),
        headers={"Content-Disposition": f"attachment; filename=\"{safe_filename}.json\""},
    )


# --- Logs (Phase 2 mandatory) ---

@router.get("/users/{user_uuid}/agentlogger/logs/grouped", response_model=GroupedLogEntriesResponse)
def admin_get_grouped_logs(user_uuid: UUID, limit: int = 20, offset: int = 0, workflow_id: Optional[str] = None, log_type: Optional[str] = None):
    """Get paginated, grouped logs for the specified user (admin view)."""
    grouped_data = get_grouped_log_entries(
        user_id=str(user_uuid), limit=limit, offset=offset, workflow_id=workflow_id, log_type=log_type
    )
    return GroupedLogEntriesResponse(**grouped_data)


@router.get("/users/{user_uuid}/agentlogger/logs/{log_id}", response_model=LogEntryResponse)
def admin_get_single_log(user_uuid: UUID, log_id: str):
    """Get a single log by ID for the specified user (admin view)."""
    log = get_log_entry(log_id, user_id=str(user_uuid))
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Log {log_id} not found")
    return LogEntryResponse(log_entry=log.model_dump())


@router.get("/users/{user_uuid}/agentlogger/logs/costs", response_model=CostHistoryResponse)
def admin_get_costs(user_uuid: UUID):
    """Get cost history logs for the specified user (admin view)."""
    logs = get_cost_history(user_id=str(user_uuid))
    total_costs = sum(log.total_cost for log in logs if getattr(log, 'total_cost', None))
    cost_entries = [
        CostLogEntry(
            start_time=log.start_time,
            step_name=getattr(log, 'step_name', None),
            model=getattr(log, 'model', None),
            total_tokens=getattr(log, 'total_tokens', None),
            total_cost=getattr(log, 'total_cost', None),
        )
        for log in logs
    ]
    return CostHistoryResponse(costs=cost_entries, total_costs=total_costs)



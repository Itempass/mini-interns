import logging
from fastapi import APIRouter, HTTPException, Query
from agentlogger.src.client import get_all_log_entries, get_log_entry, add_review, get_grouped_log_entries
from api.types.api_models.agentlogger import LogEntryResponse, LogEntriesResponse, AddReviewRequest, GroupedLogEntriesResponse
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/agentlogger/logs/grouped", response_model=GroupedLogEntriesResponse)
def get_grouped_logs(
    limit: int = Query(20, ge=1, le=100), 
    offset: int = Query(0, ge=0),
    workflow_id: Optional[str] = Query(None)
):
    """
    Get paginated, grouped logs from the agent logger database.
    """
    try:
        grouped_data = get_grouped_log_entries(limit=limit, offset=offset, workflow_id=workflow_id)
        return GroupedLogEntriesResponse(**grouped_data)
    except Exception as e:
        logger.error(f"Error fetching grouped logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/agentlogger/logs", response_model=LogEntriesResponse)
def get_all_logs():
    """
    Get all logs from the agent logger database.
    """
    try:
        logs = get_all_log_entries()
        return LogEntriesResponse(
            log_entries=[log.model_dump() for log in logs],
            count=len(logs)
        )
    except Exception as e:
        logger.error(f"Error fetching logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/agentlogger/logs/{log_id}", response_model=LogEntryResponse)
def get_single_log(log_id: str):
    """
    Get a single log by ID from the agent logger database.
    """
    try:
        log = get_log_entry(log_id)
        if log is None:
            raise HTTPException(status_code=404, detail=f"Log {log_id} not found")
        
        return LogEntryResponse(log_entry=log.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching log {log_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/agentlogger/logs/{log_id}/review")
def add_log_review(log_id: str, review_request: AddReviewRequest):
    """
    Add a review to a log.
    """
    try:
        result = add_review(log_id, review_request.feedback, review_request.needs_review, review_request.log_data)
        if not result.get("success"):
            error_detail = result.get("error", "Failed to add review.")
            if "not found" in error_detail:
                raise HTTPException(status_code=404, detail=error_detail)
            raise HTTPException(status_code=500, detail=error_detail)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding review to log {log_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

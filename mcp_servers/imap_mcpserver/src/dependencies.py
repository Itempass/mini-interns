from uuid import UUID

from fastapi import HTTPException
from fastmcp import Context
from fastmcp.server.dependencies import get_http_headers
from pydantic import BaseModel


class UserAndWorkflowContext(BaseModel):
    user_id: UUID
    workflow_uuid: UUID


def get_context_from_headers() -> UserAndWorkflowContext:
    """
    Dependency to extract user_id and workflow_uuid from request headers.
    """
    headers = get_http_headers()
    user_id_str = headers.get("x-user-id")
    workflow_uuid_str = headers.get("x-workflow-uuid")

    if not user_id_str:
        raise HTTPException(
            status_code=400,
            detail="Missing X-User-ID header",
        )
    
    # The workflow UUID is not strictly required for all MCPs, so we can handle its absence.
    if not workflow_uuid_str:
        # You could raise an error, or use a default/None value.
        # For now, let's raise, but this can be changed.
        raise HTTPException(
            status_code=400,
            detail="Missing X-Workflow-UUID header",
        )


    try:
        return UserAndWorkflowContext(
            user_id=UUID(user_id_str),
            workflow_uuid=UUID(workflow_uuid_str),
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid format for X-User-ID or X-Workflow-UUID headers",
        ) 
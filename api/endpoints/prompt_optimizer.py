from typing import List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from starlette.requests import Request
from fastapi.responses import StreamingResponse
from io import BytesIO
import json
from fastapi import BackgroundTasks

from prompt_optimizer import client as prompt_optimizer_client
from prompt_optimizer import service, database
from prompt_optimizer.models import EvaluationTemplate, EvaluationTemplateCreate, EvaluationTemplateLight, EvaluationRun
from datetime import datetime, timezone
from api.endpoints.auth import get_current_user
from user.models import User

router = APIRouter()

# --- New Dynamic Data Source Endpoints ---

@router.get(
    "/evaluation/data-sources",
    summary="List available data sources",
    response_model=List[Dict[str, str]]
)
async def list_data_sources():
    """
    Returns a list of available data sources that can be used to create
    evaluation templates. Each source has an `id` and a `name`.
    """
    return prompt_optimizer_client.list_data_sources()

@router.get(
    "/evaluation/data-sources/{source_id}/config-schema",
    summary="Get the configuration schema for a data source",
    response_model=Dict[str, Any]
)
async def get_data_source_config_schema(
    source_id: str,
    user: User = Depends(get_current_user)
):
    """
    Returns a JSON schema that describes the necessary configuration fields
    for the specified data source. This schema can be used to dynamically
    generate a form in the frontend.
    """
    try:
        return await prompt_optimizer_client.get_config_schema(source_id, user.uuid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve config schema: {e}")

class SampleRequest(BaseModel):
    config: Dict[str, Any]

@router.post(
    "/evaluation/data-sources/{source_id}/sample",
    summary="Fetch a sample data item from a data source",
    response_model=Dict[str, Any]
)
async def fetch_data_source_sample(
    source_id: str,
    request: SampleRequest,
    user: User = Depends(get_current_user)
):
    """
    Fetches a single sample data item from the specified data source using
    the provided configuration. This is used to help the user map data fields
    (e.g., 'input', 'ground_truth') before creating the full template.
    """
    try:
        return await prompt_optimizer_client.fetch_sample(source_id, request.config, user.uuid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sample data: {e}")

# --- Existing Template Management Endpoints ---
@router.post(
    "/evaluation/templates",
    response_model=EvaluationTemplate,
    status_code=201,
    summary="Create a new Evaluation Template"
)
def create_evaluation_template(
    create_request: EvaluationTemplateCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user)
):
    """
    Creates a new Evaluation Template.

    This endpoint creates a template record with a "processing" status,
    then adds a background task to fetch and process the actual data snapshot.
    The client should poll the template's status until it becomes "completed".
    """
    try:
        # This now only creates the template with "processing" status
        created_template = prompt_optimizer_client.create_template(create_request, user.uuid)
        
        # Add the heavy data processing to a background task
        background_tasks.add_task(
            service.process_data_snapshot_background,
            template_uuid=created_template.uuid,
            user_id=user.uuid,
            data_source_config=created_template.data_source_config,
            field_mapping_config=created_template.field_mapping_config
        )
        
        return created_template
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create evaluation template: {e}")

@router.put(
    "/evaluation/templates/{template_uuid}",
    response_model=EvaluationTemplate,
    summary="Update an existing Evaluation Template"
)
async def update_evaluation_template(
    template_uuid: UUID,
    template_update: EvaluationTemplateCreate, # Use the create model for the body
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user)
):
    """
    Updates an existing evaluation template.

    This endpoint takes the updated configuration, re-fetches the data to
    create a new static snapshot, and saves the updated template.
    """
    try:
        template = prompt_optimizer_client.get_template(template_uuid, user.uuid)
        if not template:
            raise HTTPException(status_code=404, detail="Evaluation template not found")

        # This now only updates the metadata and sets status to "processing" if needed
        updated_template = await prompt_optimizer_client.update_template(template, template_update, user.uuid)

        # If the status was set to processing, it means we need to refetch the data
        if updated_template.status == "processing":
            background_tasks.add_task(
                service.process_data_snapshot_background,
                template_uuid=updated_template.uuid,
                user_id=user.uuid,
                data_source_config=updated_template.data_source_config,
                field_mapping_config=updated_template.field_mapping_config
            )

        return updated_template
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e: # Catches the "not found" error from the DB layer
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update evaluation template: {e}")


@router.get(
    "/evaluation/templates",
    response_model=List[EvaluationTemplateLight],
    summary="List all Evaluation Templates (Lightweight)"
)
async def list_evaluation_templates(user: User = Depends(get_current_user)):
    """
    Retrieves a lightweight list of all evaluation templates for the current user.
    This does NOT include the heavy `cached_data` field.
    """
    return prompt_optimizer_client.list_templates_light(user.uuid)

@router.get(
    "/evaluation/templates/{template_uuid}",
    response_model=EvaluationTemplate,
    summary="Get a specific Evaluation Template"
)
async def get_evaluation_template(template_uuid: UUID, user: User = Depends(get_current_user)):
    """
    Retrieves a single evaluation template by its unique ID.
    """
    template = prompt_optimizer_client.get_template(template_uuid, user.uuid)
    if not template:
        raise HTTPException(status_code=404, detail="Evaluation template not found")
    return template


class RunRequest(BaseModel):
    original_prompt: str
    original_model: str

@router.post("/evaluation/templates/{template_id}/run", response_model=EvaluationRun, status_code=202)
async def run_evaluation(
    template_id: UUID,
    run_request: RunRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """
    Creates an EvaluationRun record and initiates the evaluation in the background.
    """
    # Verify the template exists and belongs to the user
    template = database.get_evaluation_template(template_id, user.uuid)
    if not template:
        raise HTTPException(status_code=404, detail="Evaluation template not found")

    # 1. Create the run record in a 'pending' state FIRST.
    new_run = EvaluationRun(
        user_id=user.uuid,
        template_uuid=template_id,
        original_prompt=run_request.original_prompt,
        original_model=run_request.original_model,
        status="pending",
        created_at=datetime.now(timezone.utc)
    )
    created_run = database.create_evaluation_run(new_run)
    
    # 2. Add the long-running task to the background.
    # The task will update the run record as it progresses.
    background_tasks.add_task(
        service.run_evaluation_and_refinement,
        run_uuid=created_run.uuid, # Pass the run's UUID
        user_id=user.uuid
    )
    
    # 3. Return the created run object immediately.
    return created_run


@router.get("/evaluation/runs/{run_id}", response_model=EvaluationRun)
async def get_evaluation_run_details(
    run_id: UUID,
    user: User = Depends(get_current_user)
):
    """

    Fetches the status and results of a specific evaluation run.
    """
    run = database.get_evaluation_run(run_uuid=run_id, user_id=user.uuid)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return run 

class ListThreadsRequest(BaseModel):
    filters: Dict[str, Any]
    page: int = 1
    page_size: int = 50

class CollectIdsRequest(BaseModel):
    filters: Dict[str, Any]
    limit: int

@router.post(
    "/evaluation/data-sources/{source_id}/threads/list",
    summary="List lightweight threads for selection with pagination"
)
async def list_threads_for_selection(
    source_id: str,
    request: ListThreadsRequest,
    user: User = Depends(get_current_user)
):
    try:
        return await service.list_threads(
            source_id=source_id,
            filters=request.filters,
            page=request.page,
            page_size=request.page_size,
            user_id=user.uuid
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list threads: {e}")


@router.post(
    "/evaluation/data-sources/{source_id}/threads/collect-ids",
    summary="Collect up to N message IDs across filters for bulk selection",
)
async def collect_thread_ids(
    source_id: str,
    request: CollectIdsRequest,
    user: User = Depends(get_current_user)
):
    try:
        limit = max(0, min(request.limit, 500))
        ids = await service.collect_thread_ids(
            source_id=source_id,
            filters=request.filters,
            limit=limit,
            user_id=user.uuid,
        )
        return {"ids": ids}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect ids: {e}")


class ExportRequest(BaseModel):
    selected_ids: List[str] | None = None
    selected_uids: List[str] | None = None

@router.post(
    "/evaluation/data-sources/{source_id}/export",
    summary="Export selected threads as JSON",
)
async def export_selected_threads(
    source_id: str,
    request: ExportRequest,
    user: User = Depends(get_current_user)
):
    try:
        # Prefer uids if provided
        selected = request.selected_uids if request.selected_uids else (request.selected_ids or [])
        dataset = await service.export_threads_dataset(
            source_id=source_id,
            selected_ids=selected,
            user_id=user.uuid
        )
        # Return as an attachment for download
        json_bytes = BytesIO()
        json_bytes.write(bytes(json.dumps(dataset, indent=2), 'utf-8'))
        json_bytes.seek(0)
        filename = f"dataset_{source_id}.json"
        return StreamingResponse(
            json_bytes,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\""
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export dataset: {e}")


# --- Export job (polling) endpoints ---

class StartExportJobRequest(BaseModel):
    selected_ids: List[str] | None = None
    selected_uids: List[str] | None = None

@router.post(
    "/evaluation/data-sources/{source_id}/export/jobs",
    summary="Start an export job and return job id"
)
async def start_export_job(
    source_id: str,
    request: StartExportJobRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user)
):
    try:
        selected = request.selected_uids if request.selected_uids else (request.selected_ids or [])
        if not selected:
            raise HTTPException(status_code=400, detail="No items selected")
        job_id = service.create_export_job(user.uuid, source_id, selected)
        background_tasks.add_task(service.build_export_job, job_id, user.uuid, source_id, selected)
        return {"job_id": job_id, "status": "processing"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start export job: {e}")


@router.get(
    "/evaluation/data-sources/export/jobs/{job_id}",
    summary="Get export job status"
)
async def get_export_job_status(job_id: str, user: User = Depends(get_current_user)):
    status = service.get_export_job_status(user.uuid, job_id)
    if status == "not_found":
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "status": status}

@router.get(
    "/evaluation/data-sources/export/jobs/{job_id}/progress",
    summary="Get export job progress"
)
async def get_export_job_progress(job_id: str, user: User = Depends(get_current_user)):
    status = service.get_export_job_status(user.uuid, job_id)
    if status == "not_found":
        raise HTTPException(status_code=404, detail="Job not found")
    progress = service.get_export_job_progress(user.uuid, job_id)
    return {"job_id": job_id, "status": status, **progress}


@router.get(
    "/evaluation/data-sources/export/jobs/{job_id}/download",
    summary="Download export result when completed"
)
async def download_export_job(job_id: str, user: User = Depends(get_current_user)):
    status = service.get_export_job_status(user.uuid, job_id)
    if status != "completed":
        raise HTTPException(status_code=400, detail=f"Job status is {status}")
    dataset = service.get_export_job_result(user.uuid, job_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Export data not available")
    json_bytes = BytesIO(bytes(json.dumps(dataset, indent=2), 'utf-8'))
    filename = f"dataset_export_{job_id}.json"
    return StreamingResponse(
        json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    ) 
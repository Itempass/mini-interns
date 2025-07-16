from typing import List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from starlette.requests import Request

from prompt_optimizer import client as prompt_optimizer_client
from prompt_optimizer import service, database
from prompt_optimizer.models import EvaluationTemplate, EvaluationTemplateCreate, EvaluationTemplateLight, EvaluationRun
from datetime import datetime, timezone

# A dummy User model and dependency for now
class User(BaseModel):
    uuid: UUID

async def get_current_user() -> User:
    return User(uuid=UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"))


router = APIRouter()

# Placeholder for user authentication
async def get_current_user_id(request: Request) -> UUID:
    user_id_str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    try:
        return UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

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
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Returns a JSON schema that describes the necessary configuration fields
    for the specified data source. This schema can be used to dynamically
    generate a form in the frontend.
    """
    try:
        return await prompt_optimizer_client.get_config_schema(source_id, user_id)
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
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Fetches a single sample data item from the specified data source using
    the provided configuration. This is used to help the user map data fields
    (e.g., 'input', 'ground_truth') before creating the full template.
    """
    try:
        return await prompt_optimizer_client.fetch_sample(source_id, request.config, user_id)
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
async def create_evaluation_template(
    create_request: EvaluationTemplateCreate,
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Creates a new Evaluation Template.

    This endpoint is the final step in the process. It takes the user's
    complete configuration, fetches the full dataset to create a static
    snapshot, and saves the template to the database.
    """
    try:
        created_template = await prompt_optimizer_client.create_template(create_request, user_id)
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
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Updates an existing evaluation template.

    This endpoint takes the updated configuration, re-fetches the data to
    create a new static snapshot, and saves the updated template.
    """
    try:
        # Construct the full template object for the update
        full_template_data = EvaluationTemplate(
            uuid=template_uuid,
            user_id=user_id,
            name=template_update.name,
            description=template_update.description,
            data_source_config=template_update.data_source_config,
            field_mapping_config=template_update.field_mapping_config,
            # cached_data will be populated by the service
        )
        updated_template = await prompt_optimizer_client.update_template(full_template_data, user_id)
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
async def list_evaluation_templates(user_id: UUID = Depends(get_current_user_id)):
    """
    Retrieves a lightweight list of all evaluation templates for the current user.
    This does NOT include the heavy `cached_data` field.
    """
    return prompt_optimizer_client.list_templates_light(user_id)

@router.get(
    "/evaluation/templates/{template_uuid}",
    response_model=EvaluationTemplate,
    summary="Get a specific Evaluation Template"
)
async def get_evaluation_template(template_uuid: UUID, user_id: UUID = Depends(get_current_user_id)):
    """
    Retrieves a single evaluation template by its unique ID.
    """
    template = prompt_optimizer_client.get_template(template_uuid, user_id)
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
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request

from prompt_optimizer import client as prompt_optimizer_client
from prompt_optimizer.models import EvaluationTemplate, EvaluationTemplateCreate

router = APIRouter()

# This is a placeholder for your actual user authentication logic.
# In a real application, this would be replaced with a proper dependency
# that extracts the user ID from a token or session.
async def get_current_user_id(request: Request) -> UUID:
    # For now, we'll use a hardcoded user_id for development.
    # IMPORTANT: Replace this with your actual authentication system.
    user_id_str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    try:
        return UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

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

    This endpoint initiates the process of fetching data from the specified
    source, creating a static snapshot of that data, and saving the
    entire template to the database for future use.
    """
    try:
        created_template = await prompt_optimizer_client.create_template(create_request, user_id)
        return created_template
    except Exception as e:
        # In a real app, you'd have more specific error handling.
        raise HTTPException(status_code=500, detail=f"Failed to create evaluation template: {e}")

@router.get(
    "/evaluation/templates",
    response_model=List[EvaluationTemplate],
    summary="List all Evaluation Templates"
)
async def list_evaluation_templates(user_id: UUID = Depends(get_current_user_id)):
    """
    Retrieves a list of all evaluation templates available to the current user.
    """
    return prompt_optimizer_client.list_templates(user_id)

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
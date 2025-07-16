from typing import List, Optional, Dict, Any
from uuid import UUID

from . import database, service
from .models import EvaluationTemplate, EvaluationTemplateCreate, EvaluationTemplateLight

# --- New Dynamic Data Source Functions ---

def list_data_sources() -> List[Dict[str, str]]:
    """
    Public client function to get the list of available data sources.
    """
    return service.list_data_sources()

async def get_config_schema(source_id: str, user_id: UUID) -> Dict[str, Any]:
    """
    Public client function to get the config schema for a data source.
    """
    return await service.get_data_source_config_schema(source_id, user_id)

async def fetch_sample(source_id: str, config: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
    """
    Public client function to fetch a sample data item.
    """
    return await service.fetch_data_source_sample(source_id, config, user_id)


# --- Existing Template Management Functions ---

def list_templates_light(user_id: UUID) -> List[EvaluationTemplateLight]:
    """
    Public client function to list lightweight evaluation templates for a user.
    """
    return database.list_evaluation_templates_light(user_id)

async def create_template(
    create_request: EvaluationTemplateCreate,
    user_id: UUID
) -> EvaluationTemplate:
    """
    Public client function to create a new Evaluation Template.
    This orchestrates fetching the data snapshot and saving the template.
    """
    return await service.create_template_with_snapshot(create_request, user_id)

async def update_template(
    template: EvaluationTemplate,
    user_id: UUID
) -> EvaluationTemplate:
    """
    Public client function to update an existing Evaluation Template.
    This orchestrates re-fetching the data snapshot and saving the template.
    """
    # Ensure the user ID matches the one making the request for security.
    if template.user_id != user_id:
        raise PermissionError("User not authorized to update this template.")
    return await service.update_template_with_snapshot(template)


def list_templates(user_id: UUID) -> List[EvaluationTemplate]:
    """
    Public client function to list all evaluation templates for a user.
    """
    return database.list_evaluation_templates(user_id)


def get_template(template_uuid: UUID, user_id: UUID) -> Optional[EvaluationTemplate]:
    """
    Public client function to retrieve a single evaluation template.
    """
    return database.get_evaluation_template(template_uuid, user_id)
 
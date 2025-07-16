from typing import List, Optional
from uuid import UUID

from . import database, service
from .models import EvaluationTemplate, EvaluationTemplateCreate


async def create_template(
    create_request: EvaluationTemplateCreate,
    user_id: UUID
) -> EvaluationTemplate:
    """
    Public client function to create a new Evaluation Template.
    This orchestrates fetching the data snapshot and saving the template.
    """
    return await service.create_template_with_snapshot(create_request, user_id)


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
 
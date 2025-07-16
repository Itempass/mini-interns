import logging
from typing import Dict, Any, List
from uuid import UUID

from mcp_servers.imap_mcpserver.src.imap_client.client import get_emails, get_all_labels
from . import database
from .models import EvaluationTemplate, EvaluationTemplateCreate

logger = logging.getLogger(__name__)

# A registry of available data fetching functions.
# This allows us to call the right function based on the 'tool' name from the config.
DATA_FETCHER_REGISTRY = {
    "imap.get_emails": get_emails,
    "imap.get_all_labels": get_all_labels,
}

async def _fetch_data_from_source(tool: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fetches data by calling the appropriate function from the registry.
    This is where the snapshot data comes from.
    """
    if tool not in DATA_FETCHER_REGISTRY:
        raise ValueError(f"Unknown data fetching tool: {tool}")

    fetcher_func = DATA_FETCHER_REGISTRY[tool]
    
    # The client functions return a list of Pydantic models (e.g., EmailMessage).
    # We need to convert them to dictionaries for consistent storage in our JSON snapshot.
    try:
        results = await fetcher_func(**params)
        # Ensure results are dicts for JSON serialization
        return [item.model_dump() for item in results]
    except Exception as e:
        logger.error(f"Error fetching data with tool '{tool}' and params {params}: {e}", exc_info=True)
        raise

async def create_template_with_snapshot(
    create_request: EvaluationTemplateCreate,
    user_id: UUID
) -> EvaluationTemplate:
    """
    Orchestrates the creation of a new EvaluationTemplate.
    1. Fetches data from the specified source.
    2. Creates the full EvaluationTemplate model with the data snapshot.
    3. Saves it to the database.
    """
    logger.info(f"Creating evaluation template '{create_request.name}' for user {user_id}")

    # Step 1: Fetch the data to create the static snapshot.
    cached_data = await _fetch_data_from_source(
        tool=create_request.data_source_config.tool,
        params=create_request.data_source_config.params
    )

    if not cached_data:
        # We might want to decide if an empty snapshot is an error or a valid case.
        # For now, let's treat it as a potential issue to be aware of.
        logger.warning(f"Evaluation template '{create_request.name}' was created with an empty data snapshot.")

    # Step 2: Create the full EvaluationTemplate object.
    new_template = EvaluationTemplate(
        user_id=user_id,
        name=create_request.name,
        description=create_request.description,
        data_source_config=create_request.data_source_config,
        field_mapping_config=create_request.field_mapping_config,
        cached_data=cached_data  # Include the fetched data as the snapshot.
    )

    # Step 3: Save the complete template to the database.
    try:
        created_template = database.create_evaluation_template(new_template)
        logger.info(f"Successfully saved new evaluation template {created_template.uuid}")
        return created_template
    except Exception as e:
        logger.error(f"Failed to save evaluation template '{create_request.name}': {e}")
        # Re-raise to be handled by the client/API layer.
        raise

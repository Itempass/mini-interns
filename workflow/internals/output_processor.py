import logging
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from workflow.internals import database as db
from workflow.internals.pydantic_utils import generate_simplified_json_schema
from workflow.models import StepOutputData

logger = logging.getLogger(__name__)


async def _generate_summary_for_output(
    raw_data: Any, custom_prompt: Optional[str] = None
) -> str:
    """
    Generates a concise summary for the raw output of a step using an LLM.
    """
    # In a real implementation, this would make a call to an LLM service.
    # For now, we'll create a simple string representation.
    # This avoids a circular dependency on the llm_client.
    if isinstance(raw_data, (dict, list)):
        # Simple serialization for structured data
        summary = f"Structured data with keys: {', '.join(raw_data.keys())}" if isinstance(raw_data, dict) else f"List with {len(raw_data)} items."
    elif isinstance(raw_data, str):
        # Truncate long strings
        summary = (raw_data[:100] + "...") if len(raw_data) > 100 else raw_data
    else:
        summary = "Unstructured data output."

    logger.info(f"Generated summary: {summary}")
    return summary


async def create_output_data(
    raw_data: Any,
    summary: str,
    user_id: UUID,
    markdown_representation: str | None = None,
) -> StepOutputData:
    """
    Creates and stores a StepOutputData object, automatically generating its schema.
    """
    # Create the object first, with a placeholder for the schema.
    # The `data_schema` field in the model is set to `exclude=True` to prevent recursion.
    output = StepOutputData(
        user_id=user_id,
        raw_data=raw_data,
        summary=summary,
        markdown_representation=markdown_representation,
    )

    # Now, generate the schema from the object itself and assign it.
    output.data_schema = generate_simplified_json_schema(output)

    print(f"GENERATED SCHEMA for output {output.uuid}:", output.data_schema)

    # Persist it to the database so it's addressable by its UUID
    await db._create_step_output_data_in_db(output, user_id)
    return output


def generate_step_summary_from_prompt(system_prompt: str) -> str:
    """
    Generates a simple, single-line summary from a step's system prompt.
    """
    if not system_prompt or not system_prompt.strip():
        return "No summary available."
    
    # Take the first non-empty line as the summary.
    first_line = system_prompt.strip().splitlines()[0]
    return (first_line[:150] + '...') if len(first_line) > 150 else first_line 
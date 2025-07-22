import logging
from typing import Any, Optional
from uuid import UUID
import json

from pydantic import BaseModel

from workflow.internals import database as db
from workflow.internals.pydantic_utils import generate_simplified_json_schema
from workflow.models import StepOutputData
from mcp_servers.tone_of_voice_mcpserver.src.services.openrouter_service import (
    openrouter_service,
)
from shared.config import settings

logger = logging.getLogger(__name__)


async def generate_summary(
    raw_data: Any, markdown_representation: Optional[str] = None
) -> str:
    """
    Generates a concise, one-line summary of the given data using an LLM.
    """
    # Hardcoded instruction for the LLM
    instruction = (
        "You are an expert at analyzing data structures and summarizing their content. "
        "Your task is to provide a concise summary (max 3 lines) "
        "that describes the data's primary content and purpose. Do not describe the data format (e.g., 'JSON object'); "
        "instead, describe what the data *is* (e.g., 'User profile information' or 'A list of email drafts')."
        "Make sure to say start your phrase with \" this data container contains \""
        "\n\nHere is the data:"
    )

    # Prepare the data content for the prompt
    data_content = ""
    if markdown_representation:
        data_content += f"\n\n--- Markdown Representation ---\n{markdown_representation[:2000]}" # Limit context
    
    # Serialize complex raw_data to JSON, otherwise use string representation
    if raw_data:
        try:
            # Use model_dump_json for Pydantic models
            if hasattr(raw_data, 'model_dump_json'):
                raw_data_str = raw_data.model_dump_json(indent=2)
            else:
                raw_data_str = json.dumps(raw_data, indent=2, default=str) # default=str for non-serializable types
        except (TypeError, OverflowError):
            raw_data_str = str(raw_data) # Fallback for complex, non-serializable objects
        
        data_content += f"\n\n--- Raw Data ---\n{raw_data_str[:2000]}" # Limit context

    if not data_content.strip():
        return "No data provided."

    try:
        summary = await openrouter_service.get_llm_response(
            prompt=data_content,
            system_prompt=instruction,
            model="google/gemini-flash-1.5",
        )
        # Post-process to ensure it's a single line
        return summary.strip().split('\n')[0]
    except Exception as e:
        logger.error(f"Error generating summary with LLM: {e}")
        # Fallback to a simple, non-LLM summary in case of an error
        if isinstance(raw_data, dict):
            return f"Structured data with keys: {', '.join(raw_data.keys())}"
        elif isinstance(raw_data, list):
            return f"List with {len(raw_data)} items."
        elif isinstance(raw_data, str):
            return (raw_data[:100] + "...") if len(raw_data) > 100 else raw_data
        else:
            return "Unstructured data output."


async def create_output_data(
    markdown_representation: str,
    user_id: UUID,
) -> StepOutputData:
    """
    Creates a StepOutputData object. In our new simplified system,
    this just involves creating the object with the markdown and user_id.
    """
    return StepOutputData(
        user_id=user_id,
        markdown_representation=markdown_representation,
    )


def generate_step_summary_from_prompt(system_prompt: str) -> str:
    """
    Generates a simple, single-line summary from a step's system prompt.
    """
    if not system_prompt or not system_prompt.strip():
        return "No summary available."
    
    # Take the first non-empty line as the summary.
    first_line = system_prompt.strip().splitlines()[0]
    return (first_line[:150] + '...') if len(first_line) > 150 else first_line 
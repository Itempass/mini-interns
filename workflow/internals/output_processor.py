import logging
from typing import Any, Optional

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
    raw_data: Any, summary_prompt: Optional[str] = None
) -> StepOutputData:
    """
    Creates a StepOutputData object from raw data, including a generated summary.

    Args:
        raw_data: The raw output from a step execution.
        summary_prompt: An optional prompt to guide the summary generation.

    Returns:
        A fully populated StepOutputData object.
    """
    summary = await _generate_summary_for_output(
        raw_data=raw_data, custom_prompt=summary_prompt
    )

    # The markdown representation could be generated here in the future
    # For now, we'll leave it empty.
    markdown_representation = f"## Step Output\n\n**Summary:** {summary}\n\n```json\n{raw_data}\n```"

    output = StepOutputData(
        raw_data=raw_data,
        summary=summary,
        markdown_representation=markdown_representation,
    )
    logger.info(f"Created StepOutputData object {output.uuid} with summary.")
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
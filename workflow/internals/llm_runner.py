import logging
from typing import Any
from datetime import datetime

from mcp_servers.tone_of_voice_mcpserver.src.services.openrouter_service import (
    openrouter_service,
)
from workflow.internals.output_processor import create_output_data
from workflow.models import CustomLLM, CustomLLMInstanceModel, MessageModel, StepOutputData

logger = logging.getLogger(__name__)


async def run_llm_step(
    instance: CustomLLMInstanceModel,
    llm_definition: CustomLLM,
    resolved_system_prompt: str,
    user_id: str,
) -> CustomLLMInstanceModel:
    """
    Executes a CustomLLM step.

    Args:
        instance: The specific instance of the LLM step to run.
        llm_definition: The definition of the LLM step.
        resolved_system_prompt: The fully resolved system prompt.

    Returns:
        The updated instance with the output and messages.
    """
    logger.info(f"Executing LLM step for instance {instance.uuid}")

    # The instance messages will be used to build the conversation history.
    # For a simple LLM step, we start with the resolved system prompt.
    instance.messages = [
        MessageModel(role="system", content=resolved_system_prompt),
        MessageModel(role="user", content="Proceed as instructed."),
    ]

    # Use the OpenRouter service to get the LLM response
    response_content = await openrouter_service.get_llm_response(
        prompt="Proceed as instructed.",
        system_prompt=resolved_system_prompt,
        model=llm_definition.model,
    )

    # Add the response to the messages
    instance.messages.append(MessageModel(role="assistant", content=response_content))

    # Package the result into a standard StepOutputData object
    instance.output = await create_output_data(
        raw_data=response_content,
        summary=f"LLM generated content: {response_content[:150]}...",
        user_id=user_id,
    )
    instance.status = "completed"
    instance.finished_at = datetime.utcnow()

    # Return the final instance
    return instance 
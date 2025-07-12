import logging
from typing import Any

from mcp_servers.tone_of_voice_mcpserver.src.services.openrouter_service import (
    openrouter_service,
)
from workflow.models import CustomLLM, CustomLLMInstanceModel, MessageModel

logger = logging.getLogger(__name__)


async def run_llm_step(
    instance: CustomLLMInstanceModel,
    llm_definition: CustomLLM,
    resolved_system_prompt: str,
) -> Any:
    """
    Executes a CustomLLM step.

    Args:
        instance: The specific instance of the LLM step to run.
        llm_definition: The definition of the LLM step.
        resolved_system_prompt: The fully resolved system prompt.

    Returns:
        The raw output from the language model.
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

    # Return the final content as the raw output
    return response_content 
import logging
from typing import Any

from mcp_servers.tone_of_voice_mcpserver.src.services.openrouter_service import (
    get_openrouter_llm_client,
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

    llm_client_instance = get_openrouter_llm_client(
        model_name=llm_definition.model,
    )

    # The instance messages will be used to build the conversation history.
    # For a simple LLM step, we start with the resolved system prompt.
    instance.messages = [
        MessageModel(role="system", content=resolved_system_prompt),
        MessageModel(role="user", content="Proceed as instructed."),
    ]

    response = await llm_client_instance.chat.completions.create(
        messages=[msg.model_dump() for msg in instance.messages],
    )

    response_message = response.choices[0].message
    instance.messages.append(MessageModel.model_validate(response_message.model_dump()))

    # Return the final content as the raw output
    return response_message.content 
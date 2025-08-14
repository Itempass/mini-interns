import logging
from typing import Any, Dict, List
from uuid import UUID, uuid4

from user.exceptions import InsufficientBalanceError
from shared.services.openrouterservice.client import chat as llm_chat

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Custom exception for LLM client errors."""
    pass


async def call_llm(
    prompt: str,
    user_id: UUID,
    model: str = "google/gemini-2.5-flash",
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """
    Makes a single, ad-hoc call to a specified language model using OpenRouter.
    This function now uses the centralized billing chat.
    """
    try:
        result = await llm_chat(
            call_uuid=uuid4(),
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            user_id=user_id,
        )
    except InsufficientBalanceError as e:
        logger.warning(f"Blocking LLM call for user {user_id} due to insufficient funds.")
        raise LLMClientError(str(e))
    except Exception as e:
        logger.error(f"An unexpected error occurred during the LLM call to {model}: {e}", exc_info=True)
        raise LLMClientError(f"An unexpected error occurred: {e}")

    if not result.response_text:
        logger.error(f"OpenRouter call to {model} returned an empty or invalid response: {result.raw_response}")
        raise LLMClientError("LLM response was empty or invalid.")

    logger.info(f"LLM call successful. Response length: {len(result.response_text)}")
    return result.response_text
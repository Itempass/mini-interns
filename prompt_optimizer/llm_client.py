import logging
from typing import Any, Dict, List
import httpx

from shared.config import settings

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Custom exception for LLM client errors."""
    pass


async def call_llm(
    prompt: str,
    model: str = "google/gemini-2.5-flash",
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """
    Makes a single, ad-hoc call to a specified language model using OpenRouter.

    Args:
        prompt: The full system prompt to send to the model.
        model: The identifier of the model to use (e.g., from OpenRouter).
        temperature: The creativity of the response.
        max_tokens: The maximum number of tokens for the response.

    Returns:
        The content of the model's response as a string.

    Raises:
        LLMClientError: If the API call fails or returns an unexpected response.
    """
    if not settings.OPENROUTER_API_KEY:
        raise LLMClientError("OPENROUTER_API_KEY not found in settings.")

    logger.info(f"Making LLM call to OpenRouter model: {model}")
    
    messages = [{"role": "user", "content": prompt}]
    json_payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=json_payload
            )
            response.raise_for_status()
            
            response_data = response.json()
            if not response_data.get("choices") or not response_data["choices"][0].get("message", {}).get("content"):
                logger.error(f"OpenRouter call to {model} returned an empty or invalid response: {response.text}")
                raise LLMClientError("LLM response was empty or invalid.")

            response_content = response_data["choices"][0]["message"]["content"]
            logger.info(f"LLM call successful. Response length: {len(response_content)}")
            return response_content

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError calling OpenRouter: {e}")
            logger.error(f"Request body: {json_payload}")
            if e.response:
                logger.error(f"Response text: {e.response.text}")
            raise LLMClientError(f"HTTP request failed: {e.response.status_code if e.response else 'No response'}")
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Error parsing OpenRouter response: {e}")
            logger.error(f"Response body: {response.text}")
            raise LLMClientError("Failed to parse LLM response.")
        except Exception as e:
            logger.error(f"An unexpected error occurred during the LLM call to {model}: {e}", exc_info=True)
            raise LLMClientError(f"An unexpected error occurred: {e}") 
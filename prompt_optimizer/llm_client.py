import logging
from typing import Any, Dict, List
from uuid import UUID
import httpx
import asyncio
import json

from shared.config import settings
from user import client as user_client
from user.exceptions import InsufficientBalanceError

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Custom exception for LLM client errors."""
    pass


async def _get_generation_cost(generation_id: str) -> float:
    """Retrieves the cost of a specific generation from OpenRouter."""
    if not generation_id:
        return 0.0
    
    try:
        # A small delay can help ensure the generation data is available.
        await asyncio.sleep(2)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://openrouter.ai/api/v1/generation?id={generation_id}",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"}
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"PROMPT_OPTIMIZER: Received cost data for generation {generation_id}: {json.dumps(data)}")
            return data.get("data", {}).get("total_cost", 0.0)
    except Exception as e:
        logger.error(f"Failed to retrieve cost for generation {generation_id}: {e}")
        return 0.0


async def call_llm(
    prompt: str,
    user_id: UUID,
    model: str = "google/gemini-2.5-flash",
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """
    Makes a single, ad-hoc call to a specified language model using OpenRouter.
    This function now includes a balance check and cost deduction.
    """
    if not settings.OPENROUTER_API_KEY:
        raise LLMClientError("OPENROUTER_API_KEY not found in settings.")

    logger.info(f"Checking balance for user {user_id} before making LLM call to {model}")
    try:
        user_client.check_user_balance(user_id)
    except InsufficientBalanceError as e:
        logger.warning(f"Blocking LLM call for user {user_id} due to insufficient funds.")
        raise LLMClientError(str(e)) # Re-raise as LLMClientError to be handled by the service layer

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

            generation_id = response_data.get("id")
            
            # --- Cost Deduction ---
            if generation_id:
                cost = await _get_generation_cost(generation_id)
                if cost > 0:
                    logger.info(f"Deducting cost of {cost} from user {user_id}'s balance.")
                    user_client.deduct_from_balance(user_id, cost)

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
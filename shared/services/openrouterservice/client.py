from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx

from shared.config import settings
from .models import LLMCallResult
from user import client as user_client

async def _get_generation_cost(generation_id: str) -> float:
    """Retrieve total cost for a generation directly from OpenRouter.

    Returns 0.0 on failure; errors are logged.
    """
    try:
        # Small delay to allow provider to finalize metering
        await asyncio.sleep(2)
        async with httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=60,
        ) as client:
            response = await client.get(f"/generation?id={generation_id}")
            response.raise_for_status()
            data = response.json()
        generation_data = data.get("data", {})
        return generation_data.get("total_cost", 0.0)
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPStatusError getting generation cost for id {generation_id}: {e}")
        try:
            logger.error(f"Response body: {e.response.text}")
        except Exception:
            pass
        return 0.0
    except Exception as e:
        logger.error(f"Error retrieving generation cost for id {generation_id}: {e}")
        return 0.0


logger = logging.getLogger(__name__)


async def chat(
    *,
    call_uuid: UUID,
    messages: List[Dict[str, Any]],
    model: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    response_format_json: bool = False,
    user_id: UUID,
    step_name: Optional[str] = None,
    workflow_uuid: Optional[UUID] = None,
    workflow_instance_uuid: Optional[UUID] = None,
) -> LLMCallResult:
    """Call OpenRouter chat completions and return a standardized LLMCallResult.

    Usage patterns:
    - Unstructured response (default):
      - Call with the default `response_format_json=False` and read `result.response_text`.
    - Structured response (JSON contract):
      - Call with `response_format_json=True` to request JSON mode from the provider.
      - Then parse `result.response_text` via `json.loads(...)` at the call site
        (and optionally validate with your own Pydantic model). This keeps the
        client simple while supporting structured contracts when needed.

    Notes:
    - Tools/function-calls are supported via `tools` and `tool_choice`. The
      selected tool call (if any) will be present in `result.response_message`.
    - Billing: this function will check balance before the call and, if a
      generation ID is returned, retrieve the cost and deduct it from the
      user's balance. A `user_id` is required.
    """
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not found in settings.")

    start_time = datetime.utcnow()

    # Balance check (always)
    user_client.check_user_balance(user_id)

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools is not None:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if response_format_json:
        payload["response_format"] = {"type": "json_object"}

    try:
        async with httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120,
        ) as client:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

        usage = data.get("usage", {}) or {}
        choices = data.get("choices", [])
        first_message = choices[0].get("message") if choices else None
        generation_id = data.get("id")
        total_cost: Optional[float] = None

        # Retrieve and deduct cost
        if generation_id:
            try:
                total_cost = await _get_generation_cost(generation_id)
                if total_cost and total_cost > 0:
                    user_client.deduct_from_balance(user_id, total_cost)
            except Exception as e:
                logger.error(f"Failed to retrieve or deduct cost for generation {generation_id}: {e}")

        result = LLMCallResult(
            uuid=call_uuid,
            user_id=user_id,
            model=model,
            generation_id=generation_id,
            step_name=step_name,
            workflow_uuid=workflow_uuid,
            workflow_instance_uuid=workflow_instance_uuid,
            start_time=start_time,
            end_time=datetime.utcnow(),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            total_cost=total_cost,
            response_text=(first_message or {}).get("content") if first_message else None,
            response_message=first_message,
            raw_response=data,
        )
        return result

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPStatusError calling OpenRouter: {e}")
        try:
            logger.error(f"Response body: {e.response.text}")
        except Exception:
            pass
        raise
    except Exception as e:
        logger.error(f"Unexpected error during OpenRouter chat call: {e}")
        raise



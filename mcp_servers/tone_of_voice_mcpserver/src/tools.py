import json
import logging
import asyncio
from typing import Dict, Any, List

from .mcp_builder import mcp_builder
from .dependencies import get_context_from_headers
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys

logger = logging.getLogger(__name__)

@mcp_builder.tool()
async def get_tone_of_voice_profile(language: str) -> Dict[str, Any]:
    """
    Retrieves the pre-analyzed tone of voice profile for a specific language.
    The language must be a 2-letter ISO 639-1 code (e.g., 'en', 'de', 'fr').
    """
    redis_client = get_redis_client()
    context = get_context_from_headers()
    try:
        # Get the user-specific key for the tone profile
        profile_key = RedisKeys.get_tone_of_voice_profile_key(context.user_id)

        # redis-py client is synchronous, run it in an executor to not block the event loop
        loop = asyncio.get_running_loop()
        tone_profile_raw = await loop.run_in_executor(
            None, redis_client.get, profile_key
        )
        
        if not tone_profile_raw:
            return {"error": "Tone of voice profile has not been generated yet."}

        # The profile is stored as a JSON string.
        tone_profile_data = json.loads(tone_profile_raw)

        available_languages = list(tone_profile_data.keys())

        if language in tone_profile_data:
            # The value for each language key is the profile string itself.
            profile_text = tone_profile_data.get(language)

            if profile_text:
                 return {"tone_profile": profile_text}
            else:
                return {"error": f"Profile for language '{language}' is empty or invalid."}
        else:
            return {
                "error": f"Tone of voice profile for language '{language}' not found.",
                "available_languages": available_languages
            }

    except json.JSONDecodeError:
        logger.error("Failed to decode tone of voice profile from Redis. It might be corrupted.")
        return {"error": "Could not parse tone of voice profile data from storage."}
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching tone of voice profile: {e}")
        return {"error": "An unexpected error occurred."}

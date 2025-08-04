import asyncio
import logging
import json
from uuid import UUID
from qdrant_client import models

from shared.qdrant.qdrant_client import get_payload_field_distribution, get_diverse_set_by_filter
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.app_settings import load_app_settings
from mcp_servers.tone_of_voice_mcpserver.src.internals.tone_of_voice_analyzer import analyze_tone_for_language

logger = logging.getLogger(__name__)

MINIMUM_EMAILS_FOR_TONE_ANALYSIS = 10
DIVERSE_SET_LIMIT = 10

async def determine_user_tone_of_voice(user_uuid: UUID):
    """
    Analyzes a specific user's writing style to determine their tone of voice.
    This process is user-specific, using the user's dedicated vector collection.
    """
    logger.info(f"Starting tone of voice determination for user: {user_uuid}")
    redis_client = get_redis_client()
    status_key = RedisKeys.get_tone_of_voice_status_key(user_uuid)
    
    redis_client.set(status_key, "running")

    try:
        # 1. Get language distribution from the user's specific collection
        language_distribution = get_payload_field_distribution(
            user_uuid=user_uuid,
            field_name="language"
        )

        if not language_distribution:
            logger.warning(f"No language data for user {user_uuid}. Skipping tone analysis.")
            redis_client.set(status_key, "completed")
            return

        # 2. Filter for eligible languages
        eligible_languages = [
            lang for lang, count in language_distribution.items()
            if count >= MINIMUM_EMAILS_FOR_TONE_ANALYSIS
        ]

        if not eligible_languages:
            logger.info(f"No languages met threshold for user {user_uuid}. Skipping analysis.")
            redis_client.set(status_key, "completed")
            return

        logger.info(f"Found {len(eligible_languages)} eligible languages for user {user_uuid}: {eligible_languages}")

        # Get the user's email address from their settings
        app_settings = load_app_settings(user_uuid=user_uuid)
        user_email = app_settings.IMAP_USERNAME
        if not user_email:
            logger.error(f"Could not determine email for user {user_uuid}. Aborting tone analysis.")
            redis_client.set(status_key, "failed")
            return

        full_tone_profile = {}

        # 3. Process each eligible language
        for language in eligible_languages:
            logger.info(f"Processing language '{language}' for user {user_uuid}")
            
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(key="language", match=models.MatchValue(value=language)),
                    models.FieldCondition(key="contains_user_reply", match=models.MatchValue(value=True))
                ]
            )
            
            diverse_thread_payloads = get_diverse_set_by_filter(
                user_uuid=user_uuid,
                query_filter=query_filter,
                limit=DIVERSE_SET_LIMIT
            )

            if diverse_thread_payloads:
                emails_for_analysis = [
                    {
                        "thread_id": thread.get("thread_id"),
                        "sender": message.get("from_"),
                        "body": message.get("body_cleaned"),
                        "language": language
                    }
                    for thread in diverse_thread_payloads
                    for message in thread.get("messages", [])
                ]
                
                logger.info(f"Prepared {len(emails_for_analysis)} emails for '{language}' analysis for user {user_uuid}.")

                tone_profile = await analyze_tone_for_language(
                    language_emails=emails_for_analysis,
                    user_email=user_email,
                    language=language
                )
                
                if tone_profile:
                    logger.info(f"Generated tone profile for '{language}' for user {user_uuid}.")
                    full_tone_profile[language] = tone_profile
                else:
                    logger.warning(f"Tone analysis for '{language}' for user {user_uuid} returned no profile.")
                
            else:
                logger.warning(f"Could not select diverse set of emails for '{language}' for user {user_uuid}.")
        
        # 4. Store the final profile in Redis
        profile_key = RedisKeys.get_tone_of_voice_profile_key(user_uuid)
        if full_tone_profile:
            logger.info(f"Saving aggregated tone profile for user {user_uuid} to Redis.")
            redis_client.set(profile_key, json.dumps(full_tone_profile))
        else:
            logger.warning(f"No tone profiles generated for user {user_uuid}. Nothing to save.")

        logger.info(f"Tone of voice determination completed for user {user_uuid}.")
        redis_client.set(status_key, "completed")

    except Exception as e:
        logger.error(f"Error during tone determination for user {user_uuid}: {e}", exc_info=True)
        redis_client.set(RedisKeys.get_tone_of_voice_status_key(user_uuid), "failed")

# Example of how to run this task directly for testing
if __name__ == "__main__":
    # This example would require a hardcoded user_uuid for testing
    # For example:
    # test_user_uuid = UUID("your-test-user-uuid-here")
    # asyncio.run(determine_user_tone_of_voice(user_uuid=test_user_uuid))
    logging.basicConfig(level=logging.INFO)
    logger.info("To test this script directly, provide a user UUID.")

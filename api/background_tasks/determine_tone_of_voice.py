import asyncio
import logging
import json
from qdrant_client import models

from shared.qdrant.qdrant_client import get_payload_field_distribution, get_diverse_set_by_filter
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from mcp_servers.tone_of_voice_mcpserver.src.internals.tone_of_voice_analyzer import analyze_tone_for_language

logger = logging.getLogger(__name__)

MINIMUM_EMAILS_FOR_TONE_ANALYSIS = 10
DIVERSE_SET_LIMIT = 10

async def determine_user_tone_of_voice():
    """
    Analyzes the user's writing style to determine their tone of voice for different languages.
    
    This process involves:
    1. Identifying which languages have enough emails in the vector database.
    2. For each eligible language, selecting a diverse set of emails.
    3. (Future) Running tone analysis on the selected emails.
    """
    logger.info("Starting tone of voice determination task...")
    redis_client = get_redis_client()
    redis_client.set(RedisKeys.TONE_OF_VOICE_STATUS, "running")

    try:
        # 1. Get the distribution of languages across all email threads
        language_distribution = get_payload_field_distribution(
            collection_name="email_threads",
            field_name="language"
        )

        if not language_distribution:
            logger.warning("No language data found in the vector database. Skipping tone analysis.")
            return

        # 2. Filter for languages that meet the minimum email threshold
        eligible_languages = [
            lang for lang, count in language_distribution.items()
            if count >= MINIMUM_EMAILS_FOR_TONE_ANALYSIS
        ]

        if not eligible_languages:
            logger.info("No languages met the minimum email threshold for tone analysis.")
            return

        logger.info(f"Found {len(eligible_languages)} eligible languages for tone analysis: {eligible_languages}")

        # Get the user's email address, which is needed for the analysis
        user_email = redis_client.get(RedisKeys.IMAP_USERNAME)
        if not user_email:
            logger.error("Could not determine user email from Redis. Aborting tone analysis.")
            return

        # This dictionary will hold the tone profiles for all eligible languages
        full_tone_profile = {}

        # 3. For each eligible language, select a diverse set of emails and analyze the tone
        for language in eligible_languages:
            logger.info(f"Processing tone analysis for language: '{language}'")
            
            # Create a filter to search for emails in the current language that contain a user reply
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(key="language", match=models.MatchValue(value=language)),
                    models.FieldCondition(key="contains_user_reply", match=models.MatchValue(value=True))
                ]
            )
            
            # Get a representative set of diverse threads
            diverse_thread_payloads = get_diverse_set_by_filter(
                collection_name="email_threads",
                query_filter=query_filter,
                limit=DIVERSE_SET_LIMIT
            )

            if diverse_thread_payloads:
                # Transform the list of thread payloads into a flat list of email dicts for the analyzer
                emails_for_analysis = []
                for thread in diverse_thread_payloads:
                    for message in thread.get("messages", []):
                        emails_for_analysis.append({
                            "thread_id": thread.get("thread_id"),
                            "sender": message.get("from_"),
                            "body": message.get("body_cleaned"),
                            "language": language
                        })
                
                logger.info(f"Prepared {len(emails_for_analysis)} individual emails for '{language}' tone analysis.")

                # Call the tone analyzer for the current language
                tone_profile = await analyze_tone_for_language(
                    language_emails=emails_for_analysis,
                    user_email=user_email,
                    language=language
                )
                
                if tone_profile:
                    logger.info(f"Successfully generated tone profile for '{language}'.")
                    full_tone_profile[language] = tone_profile
                else:
                    logger.warning(f"Tone analysis for '{language}' did not return a profile.")
                
            else:
                logger.warning(f"Could not select a diverse set of emails for '{language}', though it was eligible.")
        
        # 4. Store the final aggregated profile in Redis if any profiles were generated
        if full_tone_profile:
            logger.info(f"Saving aggregated tone profile for {list(full_tone_profile.keys())} to Redis.")
            redis_client.set(RedisKeys.TONE_OF_VOICE_PROFILE, json.dumps(full_tone_profile))
        else:
            logger.warning("No tone profiles were generated. Nothing to save to Redis.")

        logger.info("Tone of voice determination task completed.")
        redis_client.set(RedisKeys.TONE_OF_VOICE_STATUS, "completed")

    except Exception as e:
        logger.error(f"An error occurred during tone of voice determination: {e}", exc_info=True)
        redis_client.set(RedisKeys.TONE_OF_VOICE_STATUS, "failed")

# Example of how to run this task directly for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(determine_user_tone_of_voice())

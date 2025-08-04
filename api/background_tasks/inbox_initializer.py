import asyncio
import logging
from datetime import datetime
from langdetect import detect, LangDetectException
from uuid import UUID

from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_threads_bulk
from shared.qdrant.qdrant_client import upsert_points, generate_qdrant_point_id
from qdrant_client import models
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.services.embedding_service import get_embedding
from api.background_tasks.determine_tone_of_voice import determine_user_tone_of_voice
from shared.config import VECTORIZATION_VERSION

logger = logging.getLogger(__name__)

BATCH_SIZE = 10

def _detect_language(text: str) -> str:
    """Detects the language of a given text."""
    if not text or not text.strip():
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        logger.warning("Language detection failed for a text snippet.")
        return "unknown"

async def initialize_inbox(user_uuid: UUID):
    """
    Initializes a specific user's inbox by fetching recent email threads,
    vectorizing them, and storing them in their dedicated Qdrant collection.
    This process can be interrupted.
    """
    logger.info(f"Starting inbox initialization for user: {user_uuid}")
    redis_client = get_redis_client()
    
    # User-specific keys
    interruption_key = RedisKeys.get_inbox_vectorization_interrupted_key(user_uuid)
    status_key = RedisKeys.get_inbox_initialization_status_key(user_uuid)
    tone_status_key = RedisKeys.get_tone_of_voice_status_key(user_uuid)

    # Ensure the interruption flag is clear before we start
    redis_client.delete(interruption_key)
    redis_client.set(status_key, "running")
    redis_client.set(tone_status_key, "running")
    
    try:
        # Step 1: Fetch threads from "Sent Mail"
        logger.info(f"Fetching sent threads for user {user_uuid}...")
        sent_threads, sent_timing = await get_recent_threads_bulk(
            user_uuid=user_uuid,
            target_thread_count=300, 
            max_age_months=6, 
            source_folder_attribute='\\Sent'
        )
        logger.info(f"Fetched {len(sent_threads)} sent threads for user {user_uuid} in {sent_timing.get('total_time', 0):.2f}s")

        # Check for interruption
        if redis_client.exists(interruption_key):
            logger.warning(f"Interruption signal for user {user_uuid}. Stopping.")
            return

        # Step 2: Fetch threads from "All Mail"
        logger.info(f"Fetching all mail threads for user {user_uuid}...")
        all_mail_threads, all_mail_timing = await get_recent_threads_bulk(
            user_uuid=user_uuid,
            target_thread_count=300, 
            max_age_months=6, 
            source_folder_attribute='\\All'
        )
        logger.info(f"Fetched {len(all_mail_threads)} all mail threads for user {user_uuid} in {all_mail_timing.get('total_time', 0):.2f}s")
        
        # Step 3: Combine and deduplicate
        all_threads = sent_threads + all_mail_threads
        unique_threads_map = {thread.thread_id: thread for thread in all_threads}
        recent_threads = list(unique_threads_map.values())
        logger.info(f"Total unique threads for user {user_uuid}: {len(recent_threads)}")

        if not recent_threads:
            logger.info(f"No recent threads found for user {user_uuid}. Initialization complete.")
            redis_client.set(status_key, "completed") # Mark as completed, not failed
            return

        # Check for interruption
        if redis_client.exists(interruption_key):
            logger.warning(f"Interruption signal for user {user_uuid} after fetch. Stopping.")
            redis_client.delete(interruption_key)
            return

        points_batch = []
        successful_threads = 0

        for i, thread in enumerate(recent_threads):
            if i % BATCH_SIZE == 0:
                if redis_client.exists(interruption_key):
                    logger.warning(f"Interruption signal for user {user_uuid} during processing. Stopping.")
                    redis_client.delete(interruption_key)
                    return

            try:
                thread_markdown = thread.markdown
                if thread_markdown.strip():
                    embedding = get_embedding(f"embed this email thread, focus on the meaning of the conversation: {thread_markdown}", user_uuid=user_uuid)
                    point_id = generate_qdrant_point_id(thread.thread_id)
                    messages_payload = [{"from_": msg.from_, "date": msg.date, "body_cleaned": msg.body_cleaned, "type": msg.type} for msg in thread.messages]
                    
                    point = models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "thread_id": thread.thread_id,
                            "thread_markdown": thread_markdown,
                            "messages": messages_payload,
                            "language": _detect_language(thread_markdown),
                            "message_count": thread.message_count,
                            "subject": thread.subject,
                            "participants": thread.participants,
                            "last_message_date": thread.last_message_date,
                            "folders": thread.folders,
                            "contains_user_reply": thread.contains_user_reply
                        }
                    )
                    points_batch.append(point)
                    successful_threads += 1

                    if len(points_batch) >= BATCH_SIZE:
                        if redis_client.exists(interruption_key):
                            logger.warning(f"Interruption signal for user {user_uuid} before upload. Stopping.")
                            redis_client.delete(interruption_key)
                            return
                            
                        logger.info(f"Upserting batch of {len(points_batch)} points for user {user_uuid}.")
                        upsert_points(user_uuid=user_uuid, points=points_batch)
                        points_batch = []

            except Exception as e:
                logger.error(f"Error processing thread {thread.thread_id} for user {user_uuid}: {e}", exc_info=True)

        if points_batch:
            if redis_client.exists(interruption_key):
                logger.warning(f"Interruption signal for user {user_uuid} before final upload. Stopping.")
                redis_client.delete(interruption_key)
                return
                
            logger.info(f"Upserting remaining {len(points_batch)} points for user {user_uuid}.")
            upsert_points(user_uuid=user_uuid, points=points_batch)

        if successful_threads == 0 and recent_threads:
            redis_client.set(status_key, "failed")
            raise ValueError(f"Failed to process any threads for user {user_uuid}.")

        if redis_client.exists(interruption_key):
            logger.warning(f"Interruption signal for user {user_uuid} before completion. Aborting.")
            redis_client.delete(interruption_key)
            return

        logger.info(f"Inbox initialization completed for user: {user_uuid}")
        redis_client.set(status_key, "completed")
        redis_client.set(RedisKeys.VECTORIZATION_DATA_VERSION, VECTORIZATION_VERSION) # This remains global
        
        logger.info(f"Kicking off tone of voice analysis for user {user_uuid}.")
        asyncio.create_task(determine_user_tone_of_voice(user_uuid=user_uuid))

    except Exception as e:
        logger.error(f"Inbox initialization failed for user {user_uuid}: {e}", exc_info=True)
        redis_client.set(RedisKeys.get_inbox_initialization_status_key(user_uuid), "failed")
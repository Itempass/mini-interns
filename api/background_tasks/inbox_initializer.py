import asyncio
import logging
from datetime import datetime
from langdetect import detect, LangDetectException

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

async def initialize_inbox():
    """
    Initializes the user's inbox by fetching recent email threads using the client,
    vectorizing their markdown content, and storing them in Qdrant.
    This process can be interrupted.
    """
    logger.info("Starting inbox initialization...")
    redis_client = get_redis_client()
    
    # Ensure the interruption flag is clear before we start
    redis_client.delete(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED)
    redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "running")
    redis_client.set(RedisKeys.TONE_OF_VOICE_STATUS, "running")
    
    try:
        # Step 1: Fetch threads from "Sent Mail" to prioritize user-involved conversations
        logger.info("Fetching recent threads from Sent Mail...")
        sent_threads, sent_timing = await get_recent_threads_bulk(
            target_thread_count=300, 
            max_age_months=6, 
            source_folder_attribute='\\Sent'
        )
        logger.info(f"Fetched {len(sent_threads)} threads from Sent Mail in {sent_timing.get('total_time', 0):.2f}s")

        # Check for interruption after the first fetch
        if redis_client.exists(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED):
            logger.warning("Interruption signal received after sent mail fetch. Stopping.")
            return

        # Step 2: Fetch threads from "All Mail" for comprehensive coverage
        logger.info("Fetching recent threads from All Mail...")
        all_mail_threads, all_mail_timing = await get_recent_threads_bulk(
            target_thread_count=300, 
            max_age_months=6, 
            source_folder_attribute='\\All'
        )
        logger.info(f"Fetched {len(all_mail_threads)} threads from All Mail in {all_mail_timing.get('total_time', 0):.2f}s")
        
        # Step 3: Combine and deduplicate threads
        all_threads = sent_threads + all_mail_threads
        unique_threads_map = {thread.thread_id: thread for thread in all_threads}
        recent_threads = list(unique_threads_map.values())
        
        logger.info(f"Combined and deduplicated threads: {len(all_threads)} -> {len(recent_threads)} unique threads.")

        # If there are no recent threads, we can consider the job done.
        if not recent_threads:
            logger.info("No recent threads found to process. Inbox initialization is complete.")
            redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "failed")
            return

        # Check for interruption immediately after the long fetch operations
        if redis_client.exists(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED):
            logger.warning("Interruption signal received after fetch. Stopping vectorization process.")
            redis_client.delete(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED)
            return

        points_batch = []
        successful_threads = 0

        for i, thread in enumerate(recent_threads):
            # Check for interruption every BATCH_SIZE items or before upserting
            if i % BATCH_SIZE == 0:
                if redis_client.exists(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED):
                    logger.warning("Interruption signal received during processing. Stopping vectorization process.")
                    redis_client.delete(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED)
                    return

            try:
                # Use the thread's markdown property directly for embedding
                thread_markdown = thread.markdown
                
                if thread_markdown.strip():
                    # Generate embedding from the markdown content
                    embedding = get_embedding(f"embed this email thread, focus on the meaning of the conversation: {thread_markdown}")
                    
                    # Generate consistent point ID using the thread ID
                    point_id = generate_qdrant_point_id(thread.thread_id)
                    
                    # Create a simplified list of messages for the payload
                    messages_payload = [
                        {
                            "from_": msg.from_,
                            "date": msg.date,
                            "body_cleaned": msg.body_cleaned,
                            "type": msg.type,
                        }
                        for msg in thread.messages
                    ]
                    
                    # Create point with enriched payload
                    point = models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "thread_id": thread.thread_id,
                            "thread_markdown": thread_markdown,
                            "messages": messages_payload,
                            "language": _detect_language(thread_markdown), # Detect language from the full markdown
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
                        # Check for interruption before starting the expensive upload
                        if redis_client.exists(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED):
                            logger.warning("Interruption signal received before vector upload. Stopping vectorization process.")
                            redis_client.delete(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED)
                            return
                            
                        logger.info(f"Upserting batch of {len(points_batch)} thread points.")
                        upsert_points(collection_name="email_threads", points=points_batch)
                        points_batch = []

            except Exception as e:
                logger.error(f"Error processing thread {thread.thread_id}: {e}", exc_info=True)

        if points_batch:
            # Check for interruption before final upload
            if redis_client.exists(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED):
                logger.warning("Interruption signal received before final vector upload. Stopping vectorization process.")
                redis_client.delete(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED)
                return
                
            logger.info(f"Upserting remaining {len(points_batch)} thread points.")
            upsert_points(collection_name="email_threads", points=points_batch)

        # If we had threads to process but failed to vectorize any of them, raise an error.
        if successful_threads == 0:
            redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "failed")
            raise ValueError("Failed to process any email threads; vectorization may have failed for all of them.")

        # Check one last time before declaring success
        if redis_client.exists(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED):
            logger.warning("Interruption signal received just before completion. Aborting.")
            redis_client.delete(RedisKeys.INBOX_VECTORIZATION_INTERRUPTED)
            return

        logger.info("Inbox initialization completed successfully.")
        redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "completed")
        redis_client.set(RedisKeys.VECTORIZATION_DATA_VERSION, VECTORIZATION_VERSION)
        
        # Trigger the tone of voice analysis as a follow-up task
        logger.info("Kicking off tone of voice analysis in the background.")
        asyncio.create_task(determine_user_tone_of_voice())

    except Exception as e:
        logger.error(f"Inbox initialization failed: {e}", exc_info=True)
        redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "failed")
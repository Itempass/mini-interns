import asyncio
import logging
from datetime import datetime

from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_threads_bulk
from shared.qdrant.qdrant_client import upsert_points, generate_qdrant_point_id
from qdrant_client import models
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.services.embedding_service import get_embedding

logger = logging.getLogger(__name__)

BATCH_SIZE = 10

async def initialize_inbox():
    """
    Initializes the user's inbox by fetching recent email threads using the client,
    vectorizing their markdown content, and storing them in Qdrant.
    """
    logger.info("Starting inbox initialization...")
    redis_client = get_redis_client()
    redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "running")
    
    try:
        # Fetch recent threads using the client's bulk function
        recent_threads, timing_info = await get_recent_threads_bulk(target_thread_count=300, max_age_months=6)
        logger.info(f"Fetched {len(recent_threads)} unique threads in {timing_info.get('total_time', 0):.2f}s")

        points_batch = []

        for thread in recent_threads:
            try:
                # Use the thread's markdown property directly for embedding
                thread_markdown = thread.markdown
                
                if thread_markdown.strip():
                    # Generate embedding from the markdown content
                    embedding = get_embedding(f"embed this email thread, focus on the meaning of the conversation: {thread_markdown}")
                    
                    # Generate consistent point ID using the thread ID
                    point_id = generate_qdrant_point_id(thread.thread_id)
                    
                    # Create point with simplified payload - just store the markdown
                    point = models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "thread_id": thread.thread_id,
                            "thread_markdown": thread_markdown,
                            "message_count": thread.message_count,
                            "subject": thread.subject,
                            "participants": thread.participants,
                            "last_message_date": thread.last_message_date,
                            "folders": thread.folders
                        }
                    )
                    points_batch.append(point)

                    if len(points_batch) >= BATCH_SIZE:
                        logger.info(f"Upserting batch of {len(points_batch)} thread points.")
                        upsert_points(collection_name="email_threads", points=points_batch)
                        points_batch = []

            except Exception as e:
                logger.error(f"Error processing thread {thread.thread_id}: {e}", exc_info=True)

        if points_batch:
            logger.info(f"Upserting remaining {len(points_batch)} thread points.")
            upsert_points(collection_name="email_threads", points=points_batch)

        logger.info("Inbox initialization completed successfully.")
        redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "completed")

    except Exception as e:
        logger.error(f"Inbox initialization failed: {e}", exc_info=True)
        redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "failed")
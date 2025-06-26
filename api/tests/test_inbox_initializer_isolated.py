import asyncio
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
from contextlib import contextmanager
from unittest.mock import patch

from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_threads_bulk
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import IMAPConnectionManager
# from shared.redis.redis_client import get_redis_client
# from shared.redis.keys import RedisKeys

load_dotenv(override=True)

logger = logging.getLogger(__name__)

@contextmanager
def patch_connection_manager():
    """
    Patches the connection manager used by bulk_threading to use a test 
    connection manager initialized with environment variables, avoiding Redis.
    """
    required_vars = ["TEST_IMAP_USER", "TEST_IMAP_PASSWORD", "TEST_IMAP_SERVER"]
    if not all(os.getenv(var) for var in required_vars):
        raise EnvironmentError("Missing required IMAP environment variables in .env: TEST_IMAP_SERVER, TEST_IMAP_USER, TEST_IMAP_PASSWORD")

    test_conn_manager = IMAPConnectionManager(
        server=os.environ["TEST_IMAP_SERVER"],
        username=os.environ["TEST_IMAP_USER"],
        password=os.environ["TEST_IMAP_PASSWORD"],
    )
    
    patch_target = 'mcp_servers.imap_mcpserver.src.imap_client.internals.bulk_threading.get_default_connection_manager'
    
    with patch(patch_target, return_value=test_conn_manager) as mock:
        yield mock

BATCH_SIZE = 10

async def initialize_inbox():
    """
    Initializes the user's inbox by fetching recent email threads using the client,
    vectorizing their markdown content, and storing them in Qdrant.
    """
    logger.info("Starting inbox initialization...")
    # redis_client = get_redis_client()
    # redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "running")
    
    collected_threads = []
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
                    #embedding = get_embedding(f"embed this email thread, focus on the meaning of the conversation: {thread_markdown}")
                    
                    # Generate consistent point ID using the thread ID
                    #point_id = generate_qdrant_point_id(thread.thread_id)

                    collected_threads.append(thread) # <-- this is what we need
                    

            except Exception as e:
                logger.error(f"Error processing thread {thread.thread_id}: {e}", exc_info=True)

        if points_batch:
            logger.info(f"Upserting remaining {len(points_batch)} thread points.")
            

        logger.info("Inbox initialization completed successfully.")
        # redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "completed")
        return collected_threads

    except Exception as e:
        logger.error(f"Inbox initialization failed: {e}", exc_info=True)
        # redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "failed")
        return collected_threads

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    with patch_connection_manager():
        all_threads = asyncio.run(initialize_inbox())

    # --- Filtering Stage (Fully Isolated) ---
    if all_threads:
        target_message_id = "CAPajfh+gpXutnYeOCPjDXamDtbLoUBN1+sOycrCPjgV0YLXxMw@mail.gmail.com"
        found_thread_markdown = None

        logger.info(f"Searching for message with ID: {target_message_id} in {len(all_threads)} threads.")
        for thread in all_threads:
            for message in thread.messages:
                if message.message_id == target_message_id:
                    found_thread_markdown = thread.markdown
                    break
            if found_thread_markdown:
                break
        
        if found_thread_markdown:
            logger.info(f"--- MARKDOWN FOR THREAD CONTAINING MESSAGE {target_message_id} ---")
            print(found_thread_markdown)
            logger.info("--- END MARKDOWN ---")
        else:
            logger.warning(f"Message with ID {target_message_id} not found in any of the collected threads.")
    else:
        logger.warning("No threads were collected, skipping filtering.")
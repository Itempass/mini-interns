import asyncio
import logging
import uuid
from email_reply_parser import EmailReplyParser

from mcp_servers.imap_mcpserver.src.services.imap_service import IMAPService
from shared.qdrant.qdrant_client import upsert_points
from qdrant_client import models
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.services.embedding_service import get_embedding
from mcp_servers.imap_mcpserver.src.types.imap_models import RawEmail
from mcp_servers.imap_mcpserver.src.utils.contextual_id import parse_contextual_id

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
QDRANT_NAMESPACE_UUID = uuid.UUID('a1b2c3d4-e5f6-7890-1234-567890abcdef') # Namespace for deterministic UUIDs

def get_email_body(raw_email: RawEmail) -> str:
    """Extracts the plain text body from a RawEmail object."""
    msg = raw_email.msg
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))

            if ctype == 'text/plain' and 'attachment' not in cdispo:
                return part.get_payload(decode=True).decode('utf-8', errors='ignore')
    else:
        return msg.get_payload(decode=True).decode('utf-8', errors='ignore')
    return ""

async def initialize_inbox():
    """
    Initializes the user's inbox by fetching sent emails,
    vectorizing them, and storing them in Qdrant.
    """
    logger.info("Starting inbox initialization...")
    redis_client = get_redis_client()
    redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "running")
    
    try:
        imap_service = IMAPService()
        await asyncio.get_running_loop().run_in_executor(None, imap_service.connect)

        sent_emails = await imap_service.list_sent_emails(max_results=100)
        logger.info(f"Fetched {len(sent_emails)} sent emails.")

        points_batch = []

        for email in sent_emails:
            try:
                thread = await imap_service.fetch_email_thread(email.uid)
                logger.info(f"Fetched thread for email {email.uid} with {len(thread)} messages.")

                for message in thread:
                    body = get_email_body(message)
                    cleaned_body = EmailReplyParser.parse_reply(body)

                    if cleaned_body:
                        embedding = get_embedding(cleaned_body)
                        _, uid = parse_contextual_id(message.uid)
                        
                        # Qdrant requires a UUID or integer for the point ID.
                        # We create a deterministic UUID from the contextual message UID.
                        # That way it is always the same for the same message.
                        point_id = str(uuid.uuid5(QDRANT_NAMESPACE_UUID, message.uid))
                        
                        point = models.PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload={
                                "contextual_id": message.uid,
                                "message_id": uid
                            }
                        )
                        points_batch.append(point)

                        if len(points_batch) >= BATCH_SIZE:
                            logger.info(f"Upserting batch of {len(points_batch)} points.")
                            upsert_points(collection_name="emails", points=points_batch)
                            points_batch = []

            except Exception as e:
                logger.error(f"Error processing email {email.uid}: {e}", exc_info=True)

        if points_batch:
            logger.info(f"Upserting remaining {len(points_batch)} points.")
            upsert_points(collection_name="emails", points=points_batch)

        logger.info("Inbox initialization completed successfully.")
        redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "completed")

    except Exception as e:
        logger.error(f"Inbox initialization failed: {e}", exc_info=True)
        redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "failed")
    finally:
        if 'imap_service' in locals() and imap_service.mail:
            imap_service.disconnect()
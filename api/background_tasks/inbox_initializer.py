import asyncio
import logging
import uuid
from email_reply_parser import EmailReplyParser
from datetime import datetime

from mcp_servers.imap_mcpserver.src.services.imap_service import IMAPService
from shared.qdrant.qdrant_client import upsert_points
from qdrant_client import models
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.services.embedding_service import get_embedding
from shared.services.text_utils import clean_email_text_for_storage
from mcp_servers.imap_mcpserver.src.types.imap_models import RawEmail
from mcp_servers.imap_mcpserver.src.utils.contextual_id import parse_contextual_id
from shared.config import settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 10

def get_cleaned_email_body(raw_email: RawEmail) -> str:
    """Extracts and cleans the plain text body from a RawEmail object."""
    msg = raw_email.msg
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))

            if ctype == 'text/plain' and 'attachment' not in cdispo:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(charset, errors='ignore')
                        break
                except Exception as e:
                    logger.warning(f"Could not decode body part for email: {e}")
                    body = "[Could not decode body]"

    else:
        try:
            charset = msg.get_content_charset() or 'utf-8'
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(charset, errors='ignore')
        except Exception as e:
            logger.warning(f"Could not decode body for email: {e}")
            body = "[Could not decode body]"

    return EmailReplyParser.parse_reply(body)

def extract_email_metadata(raw_email: RawEmail) -> dict:
    """Extracts metadata from a RawEmail object."""
    msg = raw_email.msg
    
    # Get date - try to parse it, fallback to current time if parsing fails
    date_str = msg.get('Date', '')
    try:
        from email.utils import parsedate_to_datetime
        date_obj = parsedate_to_datetime(date_str) if date_str else datetime.now()
        date_iso = date_obj.isoformat()
    except Exception:
        date_iso = datetime.now().isoformat()
    
    # Extract the full body content (not cleaned) for formatting purposes
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))

            if ctype == 'text/plain' and 'attachment' not in cdispo:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(charset, errors='ignore')
                        break
                except Exception as e:
                    logger.warning(f"Could not decode body part for email: {e}")
                    body = "[Could not decode body]"
    else:
        try:
            charset = msg.get_content_charset() or 'utf-8'
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(charset, errors='ignore')
        except Exception as e:
            logger.warning(f"Could not decode body for email: {e}")
            body = "[Could not decode body]"
    
    # Clean the body text for storage using the new utility
    cleaned_body = clean_email_text_for_storage(body)
    
    return {
        'subject': msg.get('Subject', ''),
        'from': msg.get('From', ''),
        'to': msg.get('To', ''),
        'cc': msg.get('Cc', ''),
        'date': date_iso,
        'uid': raw_email.uid,
        'body': cleaned_body
    }

async def initialize_inbox():
    """
    Initializes the user's inbox by fetching recent email threads,
    vectorizing them, and storing them in Qdrant with full metadata.
    """
    logger.info("Starting inbox initialization...")
    redis_client = get_redis_client()
    redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "running")
    
    try:
        imap_service = IMAPService()

        # Fetch all unique threads in one go
        recent_threads = await imap_service.fetch_recent_threads(max_emails_to_scan=100)
        logger.info(f"Fetched {len(recent_threads)} unique threads from recent emails.")

        points_batch = []

        for thread in recent_threads:
            try:
                # Combine the content of all messages in the thread
                full_thread_content = ""
                messages = []
                
                for message in thread:
                    cleaned_body = get_cleaned_email_body(message)
                    full_thread_content += cleaned_body + "\\n\\n"
                    
                    # Create a complete message dict with metadata and UID
                    message_data = extract_email_metadata(message)
                    messages.append(message_data)

                if full_thread_content.strip():
                    embedding = get_embedding(f"embed this email, focus on the meaning of the conversation: {full_thread_content.strip()}")
                    
                    # Use the first message's UID for a stable, deterministic thread ID
                    thread_id_source = thread[0].uid
                    point_id = str(uuid.uuid5(uuid.UUID(settings.QDRANT_NAMESPACE_UUID), thread_id_source))
                    
                    # Get metadata from the first message (thread starter)
                    first_message = messages[0] if messages else {}
                    
                    point = models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "thread_id": thread_id_source,
                            "thread_content": full_thread_content.strip(),
                            "message_count": len(thread),
                            "subject": first_message.get('subject', ''),
                            "from": first_message.get('from', ''),
                            "date": first_message.get('date', ''),
                            "messages": messages
                        }
                    )
                    points_batch.append(point)

                    if len(points_batch) >= BATCH_SIZE:
                        logger.info(f"Upserting batch of {len(points_batch)} thread points.")
                        upsert_points(collection_name="email_threads", points=points_batch)
                        points_batch = []

            except Exception as e:
                # Use the UID of the first message for logging context if the thread is not empty
                thread_context = thread[0].uid if thread else "unknown"
                logger.error(f"Error processing thread starting with {thread_context}: {e}", exc_info=True)

        if points_batch:
            logger.info(f"Upserting remaining {len(points_batch)} thread points.")
            upsert_points(collection_name="email_threads", points=points_batch)

        logger.info("Inbox initialization completed successfully.")
        redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "completed")

    except Exception as e:
        logger.error(f"Inbox initialization failed: {e}", exc_info=True)
        redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "failed")
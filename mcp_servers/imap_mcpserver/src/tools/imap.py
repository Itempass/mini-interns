"""
IMAP tools for MCP server, using IMAPService.
"""

import email
import logging
import dateutil.parser
from email.header import decode_header
from typing import List, Optional, Dict, Any, Union
from email_reply_parser import EmailReplyParser

from ..mcp_builder import mcp_builder
from ..services.imap_service import IMAPService
from ..types.imap_models import RawEmail
from ..utils.contextual_id import is_valid_contextual_id
from shared.qdrant.qdrant_client import semantic_search, search_by_vector
from shared.services.embedding_service import get_embedding, rerank_documents
from shared.services.text_utils import format_email_for_display, format_thread_separator, clean_email_text_for_storage
from shared.config import settings
import uuid

# Instantiate the services that the tools will use
imap_service = IMAPService()
logger = logging.getLogger(__name__)

def _format_email_as_markdown(msg: email.message.Message, email_id: str) -> str:
    def _decode_header(header_value: str) -> str:
        if not header_value:
            return ""
        parts = decode_header(header_value)
        header_parts = []
        for part, encoding in parts:
            if isinstance(part, bytes):
                header_parts.append(part.decode(encoding or 'utf-8', errors='ignore'))
            else:
                header_parts.append(str(part))
        return "".join(header_parts)

    subject = _decode_header(msg['subject'])
    from_ = _decode_header(msg['from'])
    to = _decode_header(msg.get('to'))
    cc = _decode_header(msg.get('cc'))
    date = msg.get('date', 'N/A')

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(charset, errors='ignore')
                        break
                except Exception as e:
                    logger.warning(f"Could not decode body part for email id {email_id}: {e}")
                    body = "[Could not decode body]"
    else:
        try:
            charset = msg.get_content_charset() or 'utf-8'
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(charset, errors='ignore')
        except Exception as e:
            logger.warning(f"Could not decode body for email id {email_id}: {e}")
            body = "[Could not decode body]"

    return (
        f"## Subject: {subject}\n"
        f"* id: {email_id}\n"
        f"* from: {from_}\n"
        f"* to: {to or 'N/A'}\n"
        f"* cc: {cc or 'N/A'}\n"
        f"* date: {date}\n\n"
        f"{body.strip()}"
    )

def _format_email_reply_as_markdown(msg: email.message.Message, email_id: str) -> str:
    def _decode_header(header_value: str) -> str:
        if not header_value:
            return ""
        parts = decode_header(header_value)
        header_parts = []
        for part, encoding in parts:
            if isinstance(part, bytes):
                header_parts.append(part.decode(encoding or 'utf-8', errors='ignore'))
            else:
                header_parts.append(str(part))
        return "".join(header_parts)

    subject = _decode_header(msg['subject'])
    from_ = _decode_header(msg['from'])
    to = _decode_header(msg.get('to'))
    cc = _decode_header(msg.get('cc'))
    date = msg.get('date', 'N/A')

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(charset, errors='ignore')
                        break
                except Exception as e:
                    logger.warning(f"Could not decode body part for email id {email_id}: {e}")
                    body = "[Could not decode body]"
    else:
        try:
            charset = msg.get_content_charset() or 'utf-8'
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(charset, errors='ignore')
        except Exception as e:
            logger.warning(f"Could not decode body for email id {email_id}: {e}")
            body = "[Could not decode body]"

    return (
        f"## Subject: {subject}\n"
        f"* id: {email_id}\n"
        f"* from: {from_}\n"
        f"* to: {to or 'N/A'}\n"
        f"* cc: {cc or 'N/A'}\n"
        f"* date: {date}\n\n"
        f"{EmailReplyParser.parse_reply(body).strip()}"
    )

def _get_cleaned_email_body(raw_email: RawEmail) -> str:
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

# --- Tool Implementations ---

# @mcp_builder.tool()
async def list_inbox_emails(maxResults: Optional[int] = 10) -> List[str]:
    """Lists the user's inbox emails (excluding drafts) with basic details."""
    raw_emails: List[RawEmail] = await imap_service.list_inbox_emails(max_results=maxResults)
    return [
        _format_email_as_markdown(email_data.msg, email_data.uid)
        for email_data in raw_emails
    ]

#@mcp_builder.tool()
async def get_email(messageId: str) -> Union[str, Dict[str, Any]]:
    """Retrieves a specific email by its ID."""
    raw_email = await imap_service.get_email(message_id=messageId)
    if raw_email:
        return _format_email_as_markdown(raw_email.msg, raw_email.uid)
    return {"error": f"Email with ID {messageId} not found."}

# @mcp_builder.tool()
async def get_full_thread_for_email(messageId: str) -> Union[str, Dict[str, Any]]:
    """
    Retrieves the full email thread for a given email ID, sorts it chronologically,
    and returns it as a formatted string.
    """
    thread_emails = await imap_service.fetch_email_thread(message_id=messageId)
    if not thread_emails:
        return {"error": f"Could not retrieve thread for email ID {messageId}."}

    # Sort emails by date
    def get_date(raw_email: RawEmail):
        try:
            return dateutil.parser.parse(raw_email.msg['Date'])
        except (ValueError, TypeError):
            # Fallback for unparseable dates; sort them to the end
            return dateutil.parser.parse("1900-01-01 00:00:00+00:00")

    thread_emails.sort(key=get_date)

    # Format the entire thread into a single string
    formatted_thread = "\n\n---\n\n".join(
        _format_email_as_markdown(email.msg, email.uid)
        for email in thread_emails
    )
    
    return formatted_thread

#@mcp_builder.tool()
async def search_emails(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Searches for emails matching a query."""
    return await imap_service.search_emails(query=query, max_results=max_results)

@mcp_builder.tool()
async def draft_reply(messageId: str, body: str) -> Dict[str, Any]:
    """
    Drafts a reply to a given email and saves it in the drafts folder.
    It does NOT send the email. Draft_reply will include the signature automatically, so you do not need to include it in the body.
    """

    if not is_valid_contextual_id(messageId):
        return {"error": f"Invalid messageId format. It must be a contextual ID (e.g., 'SU5CT1g=:1234'). You must use a valid messageId from another tool."}

    return await imap_service.draft_reply(message_id=messageId, body=body)

# The following tools are not directly related to IMAP but are often used in the same context.
# They can be moved to a different service/tool file later if needed.

#@mcp_builder.tool()
async def semantic_search_emails(query: str, top_k: Optional[int] = 10) -> List[Dict[str, Any]]:
    """Performs a semantic search on emails and returns conversational context."""
    search_hits = semantic_search(
        collection_name="emails",
        query=query,
        top_k=top_k or 10
    )

    searched_emails = []
    for hit in search_hits:
        contextual_id = hit.get("contextual_id")
        if contextual_id:
            email_data = await imap_service.get_email(message_id=contextual_id)
            if email_data:
                searched_emails.append(_format_email_reply_as_markdown(email_data.msg, email_data.uid))
    
    return {"search_results": searched_emails, "llm_instructions": "Use get_full_thread_for_email to get the full thread of a search result email."}

#@mcp_builder.tool()
async def find_similar_emails(messageId: str, top_k: Optional[int] = 5) -> List[Dict[str, Any]]:
    """Finds emails with similar content to a given email and returns this message without any other messages in the thread. Use get_full_thread_for_email to get the full thread of a similar email."""
    source_email = await imap_service.get_email(message_id=messageId)
    if not source_email:
        return {"error": f"Email with ID {messageId} not found."}

    cleaned_body = _get_cleaned_email_body(source_email)
    if not cleaned_body:
        return {"error": f"Could not extract a clean body from email {messageId}."}

    embedding = get_embedding(cleaned_body)

    similar_hits = search_by_vector(
        collection_name="emails",
        query_vector=embedding,
        top_k=top_k or 5,
        exclude_contextual_id=messageId,
    )

    similar_emails = []
    for hit in similar_hits:
        contextual_id = hit.get("contextual_id")
        if contextual_id:
            email_data = await imap_service.get_email(message_id=contextual_id)
            if email_data:
                similar_emails.append(_format_email_reply_as_markdown(email_data.msg, email_data.uid))

    return {"similar_emails": similar_emails, "llm_instructions": "Use get_full_thread_for_email to get the full thread of a similar email."}

# @mcp_builder.tool()
async def find_similar_emails_with_their_reply(messageId: str, top_k: Optional[int] = 5) -> Dict[str, Any]:
    """
    Finds emails with similar content to a given email and returns each message
    paired with its direct reply, if a reply exists.
    """
    source_email = await imap_service.get_email(message_id=messageId)
    if not source_email:
        return {"error": f"Email with ID {messageId} not found."}

    cleaned_body = _get_cleaned_email_body(source_email)
    if not cleaned_body:
        return {"error": f"Could not extract a clean body from email {messageId}."}

    embedding = get_embedding(cleaned_body)

    similar_hits = search_by_vector(
        collection_name="emails",
        query_vector=embedding,
        top_k=top_k or 5,
        exclude_contextual_id=messageId,
    )

    def get_date(raw_email: RawEmail):
        try:
            return dateutil.parser.parse(raw_email.msg['Date'])
        except (ValueError, TypeError):
            # Fallback for unparseable dates; sort them to the end
            return dateutil.parser.parse("1900-01-01 00:00:00+00:00")

    similar_conversations = []
    for hit in similar_hits:
        contextual_id = hit.get("contextual_id")
        if not contextual_id:
            continue

        thread_emails = await imap_service.fetch_email_thread(message_id=contextual_id)
        if not thread_emails:
            email_data = await imap_service.get_email(message_id=contextual_id)
            if email_data:
                similar_conversations.append(_format_email_reply_as_markdown(email_data.msg, email_data.uid))
            continue

        thread_emails.sort(key=get_date)

        parent_email = next((e for e in thread_emails if e.uid == contextual_id), None)

        if not parent_email:
            # This is unlikely but as a fallback, just format the first message if it exists
            if thread_emails:
                first_email = thread_emails[0]
                similar_conversations.append(_format_email_reply_as_markdown(first_email.msg, first_email.uid))
            continue

        parent_message_id = parent_email.msg.get('Message-ID')
        reply_email = None

        if parent_message_id:
            parent_date = get_date(parent_email)
            for potential_reply in thread_emails:
                if get_date(potential_reply) <= parent_date:
                    continue

                in_reply_to = potential_reply.msg.get('In-Reply-To')
                if in_reply_to and in_reply_to.strip() == parent_message_id.strip():
                    reply_email = potential_reply
                    break

        if reply_email:
            formatted_pair = (
                f"---PARENT EMAIL---\n"
                f"{_format_email_reply_as_markdown(parent_email.msg, parent_email.uid)}\n\n"
                f"---REPLY---\n"
                f"{_format_email_reply_as_markdown(reply_email.msg, reply_email.uid)}"
            )
            similar_conversations.append(formatted_pair)
        else:
            similar_conversations.append(_format_email_reply_as_markdown(parent_email.msg, parent_email.uid))

    return {
        "similar_conversations": similar_conversations,
        "llm_instructions": "These are conversations similar to the original email. Each item contains a parent email and its direct reply, if one was found."
    }

@mcp_builder.tool()
async def find_similar_threads(messageId: str, top_k: Optional[int] = 5) -> Dict[str, Any]:
    """
    Finds email threads with similar content to the thread of a given email ID.
    Uses vector search followed by reranking for improved relevance.
    """
    # 1. Get the full thread for the source email
    source_thread = await imap_service.fetch_email_thread(message_id=messageId)
    if not source_thread:
        return {"error": f"Could not retrieve the thread for email ID {messageId} to find similar conversations."}

    # 2. Combine the content and generate a single embedding for the source thread
    full_thread_content = ""
    for message in source_thread:
        cleaned_body = _get_cleaned_email_body(message)
        # Apply the same cleaning methodology as inbox_initializer.py
        cleaned_body = clean_email_text_for_storage(cleaned_body)
        full_thread_content += cleaned_body + "\\n\\n"
    
    if not full_thread_content.strip():
        return {"error": f"Could not extract any content from the source thread of email {messageId}."}
    
    source_embedding = get_embedding(f"embed this email, focus on the meaning of the conversation: {full_thread_content.strip()}")

    # 3. Determine the Qdrant point ID of the source thread to exclude it from search results
    source_thread_id_for_qdrant = source_thread[0].uid
    source_point_id = str(uuid.uuid5(uuid.UUID(settings.QDRANT_NAMESPACE_UUID), source_thread_id_for_qdrant))

    # 4. Perform initial vector search in the 'email_threads' collection (get more results for reranking)
    initial_search_k = max(top_k * 3, 10)  # Get 3x more results for reranking
    similar_hits = search_by_vector(
        collection_name="email_threads",
        query_vector=source_embedding,
        top_k=initial_search_k,
        exclude_ids=[source_point_id],
    )

    if not similar_hits:
        return {"similar_threads": [], "llm_instructions": "No similar threads found."}

    # 5. Prepare documents for reranking using thread_content from vector search results
    thread_contents = []
    thread_metadata = []
    
    for hit in similar_hits:
        thread_content = hit.get("thread_content", "")
        messages_metadata = hit.get("messages", [])
        
        if thread_content and messages_metadata:
            thread_contents.append(thread_content)
            thread_metadata.append(messages_metadata)

    if not thread_contents:
        return {"similar_threads": [], "llm_instructions": "No valid thread content found for reranking."}

    # 6. Use reranker to improve ordering based on relevance
    try:
        reranked_results = rerank_documents(
            query="Find similar threads to the following email and contain content that is relevant to the following email: " + full_thread_content.strip(),
            documents=thread_contents,
            top_k=top_k
        )
    except Exception as e:
        logger.warning(f"Reranking failed, falling back to vector search results: {e}")
        # Fallback to original vector search results
        reranked_results = [{"index": i} for i in range(min(len(thread_contents), top_k or 3))]

    # 7. Format threads using the reranked order and stored metadata
    similar_threads_formatted = []
    
    for result in reranked_results:
        index = result["index"]
        if index < len(thread_metadata):
            messages_metadata = thread_metadata[index]
            
            # Format each message in the thread using the new utility
            formatted_messages = []
            for msg_meta in messages_metadata:
                formatted_message = format_email_for_display(
                    subject=msg_meta.get('subject', ''),
                    from_addr=msg_meta.get('from', ''),
                    to_addr=msg_meta.get('to', ''),
                    cc_addr=msg_meta.get('cc', ''),
                    date=msg_meta.get('date', 'N/A'),
                    body=msg_meta.get('body', '')
                )
                formatted_messages.append(formatted_message)
            
            # Join messages with thread separators
            formatted_thread = format_thread_separator().join(formatted_messages)
            similar_threads_formatted.append(formatted_thread)

    return {
        "similar_threads": similar_threads_formatted,
        "llm_instructions": "These are full conversation threads that are semantically similar to the original email's thread, ordered by relevance using AI reranking."
    }

# --- Non-Gmail/IMAP tools ---
#@mcp_builder.tool()
async def get_available_languages_for_tone_of_voice() -> Dict[str, Any]:
    """Gets a list of all available language profiles for the user's account's tone of voice."""
    # This would call a ToneService
    pass

#@mcp_builder.tool()
async def get_tone_of_voice(language: str) -> Union[Dict[str, Any], str]:
    """Gets the user's tone of voice description for a given language profile."""
    # This would call a ToneService
    pass 
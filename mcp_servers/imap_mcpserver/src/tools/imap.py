"""
IMAP tools for MCP server, using IMAPService.
"""

import email
import logging
import dateutil.parser
from email.header import decode_header
from typing import List, Optional, Dict, Any, Union

from ..mcp_builder import mcp_builder
from ..services.imap_service import IMAPService
from ..services.qdrant_service import QdrantService
from ..types.imap_models import RawEmail
from shared.qdrant.qdrant_client import semantic_search

# Instantiate the services that the tools will use
imap_service = IMAPService()
qdrant_service = QdrantService()
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

# --- Tool Implementations ---

@mcp_builder.tool()
async def list_inbox_emails(maxResults: Optional[int] = 10) -> List[str]:
    """Lists the user's inbox emails (excluding drafts) with basic details."""
    raw_emails: List[RawEmail] = await imap_service.list_inbox_emails(max_results=maxResults)
    return [
        _format_email_as_markdown(email_data.msg, email_data.uid)
        for email_data in raw_emails
    ]

@mcp_builder.tool()
async def get_email(messageId: str) -> Union[str, Dict[str, Any]]:
    """Retrieves a specific email by its ID."""
    raw_email = await imap_service.get_email(message_id=messageId)
    if raw_email:
        return _format_email_as_markdown(raw_email.msg, raw_email.uid)
    return {"error": f"Email with ID {messageId} not found."}

@mcp_builder.tool()
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

@mcp_builder.tool()
async def search_emails(query: str, maxResults: int = 10) -> List[Dict[str, Any]]:
    """Searches for emails matching a query."""
    return await imap_service.search_emails(query=query, max_results=maxResults)

@mcp_builder.tool()
async def draft_reply(messageId: str, body: str, cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None) -> Union[Dict[str, Any], str]:
    """Creates a draft email in response to an existing email."""
    return await imap_service.draft_reply(message_id=messageId, body=body, cc=cc, bcc=bcc)

# The following tools are not directly related to IMAP but are often used in the same context.
# They can be moved to a different service/tool file later if needed.

@mcp_builder.tool()
async def semantic_search_emails(query: str, top_k: Optional[int] = 10, user_email: Optional[str] = None) -> List[Dict[str, Any]]:
    """Performs a semantic search on emails and returns conversational context."""
    if not user_email:
        raise ValueError("user_email must be provided for semantic search.")
    
    return semantic_search(
        collection_name="emails",
        query=query,
        user_email=user_email,
        top_k=top_k or 10
    )

@mcp_builder.tool()
async def find_similar_emails(messageId: str, top_k: Optional[int] = 5) -> List[Dict[str, Any]]:
    """Finds emails with similar content to a given email and returns their conversational context."""
    # This would also likely call a different service
    pass

# --- Non-Gmail/IMAP tools ---
@mcp_builder.tool()
async def get_available_languages_for_tone_of_voice() -> Dict[str, Any]:
    """Gets a list of all available language profiles for the user's account's tone of voice."""
    # This would call a ToneService
    pass

@mcp_builder.tool()
async def get_tone_of_voice(language: str) -> Union[Dict[str, Any], str]:
    """Gets the user's tone of voice description for a given language profile."""
    # This would call a ToneService
    pass 
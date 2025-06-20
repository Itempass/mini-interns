"""
IMAP tools for MCP server, using IMAPService.
"""

from typing import List, Optional, Dict, Any, Union

from ..mcp_builder import mcp_builder
from ..services.imap_service import IMAPService

# Instantiate the service that the tools will use
imap_service = IMAPService()

# --- Tool Implementations ---

@mcp_builder.tool()
async def list_inbox_emails(maxResults: Optional[int] = 10) -> List[Dict[str, Any]]:
    """Lists the user's inbox emails (excluding drafts) with basic details."""
    return await imap_service.list_inbox_emails(max_results=maxResults)

@mcp_builder.tool()
async def get_email(messageId: str) -> Dict[str, Any]:
    """Retrieves a specific email by its ID."""
    return await imap_service.get_email(message_id=messageId)

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
async def semantic_search_emails(query: str, top_k: Optional[int] = 10) -> List[Dict[str, Any]]:
    """Performs a semantic search on emails and returns conversational context."""
    # This would likely call a different service (e.g., a vector search service)
    pass

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
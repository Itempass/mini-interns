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
from ..imap_client.client import get_message_by_id, get_complete_thread, draft_reply as client_draft_reply, set_label as client_set_label, get_recent_inbox_messages
from shared.qdrant.qdrant_client import semantic_search, search_by_vector, generate_qdrant_point_id
from shared.services.embedding_service import get_embedding, rerank_documents

# Instantiate the services that the tools will use
logger = logging.getLogger(__name__)

# --- Tool Implementations ---

@mcp_builder.tool()
async def draft_reply(messageId: str, body: str) -> Dict[str, Any]:
    """
    Drafts a reply to a given email and saves it in the drafts folder.
    It does NOT send the email. Draft_reply will include the signature automatically, so you do not need to include it in the body.
    """

    # TODO: Add validation for messageId

    # Get the original message using the client
    original_message = await get_message_by_id(messageId)
    if not original_message:
        return {"error": f"Could not find email with messageId: {messageId}"}

    # Use the client's draft_reply function
    result = await client_draft_reply(original_message, body)
    
    return result

@mcp_builder.tool()
async def set_label(messageId: str, label: str) -> Dict[str, Any]:
    """
    Adds a label to a specific email message.
    The label must already exist in Gmail. If the label does not exist, an error will be returned with a list of available labels.
    """
    if not messageId or not label:
        return {"success": False, "message": "messageId and label are required."}

    result = await client_set_label(messageId, label)
    return result

@mcp_builder.tool()
async def get_thread_for_message_id(messageId: str) -> Dict[str, Any]:
    """
    Retrieves the full email thread for a given message ID and formats it as markdown.
    """
    # 1. Get the original message using the client
    original_message = await get_message_by_id(messageId)
    if not original_message:
        return {"error": f"Could not find email with messageId: {messageId}"}

    # 2. Get the complete thread using the client
    thread = await get_complete_thread(original_message)
    if not thread:
        return {"error": f"Could not retrieve the thread for email ID {messageId}."}

    # 3. Return the thread's markdown representation
    return {"thread_markdown": thread.markdown}

@mcp_builder.tool()
async def list_most_recent_inbox_emails(count: int = 10) -> List[Dict[str, Any]]:
    """
    Lists the most recent emails from the inbox, providing a summary of each.
    """
    messages = await get_recent_inbox_messages(count)
    
    summaries = []
    for message in messages:
        summaries.append({
            "message_id": message.message_id,
            "message_uid": message.uid,
            "from": message.from_,
            "to": message.to,
            "subject": message.subject,
            "date": message.date,
            "snippet": message.body_cleaned[:250] + "..." if len(message.body_cleaned) > 250 else message.body_cleaned
        })
        
    return summaries

# The following tools are not directly related to IMAP but are often used in the same context.
# They can be moved to a different service/tool file later if needed.

@mcp_builder.tool()
async def find_similar_threads(messageId: str, top_k: Optional[int] = 5) -> str:
    """
    Finds email threads with similar content to the thread of a given email ID,
    and returns them as a single markdown formatted string.
    Uses vector search followed by reranking for improved relevance.
    """
    # 1. Get the original message using the client
    original_message = await get_message_by_id(messageId)
    if not original_message:
        return f"## Error\n\nCould not find email with messageId: {messageId}"

    # 2. Get the complete thread using the client
    source_thread = await get_complete_thread(original_message)
    if not source_thread:
        return f"## Error\n\nCould not retrieve the thread for email ID {messageId} to find similar conversations."

    # 3. Use the thread's markdown property for embedding - it's already formatted and cleaned
    thread_markdown = source_thread.markdown
    if not thread_markdown.strip():
        return f"## Error\n\nCould not extract any content from the source thread of email {messageId}."
    
    source_embedding = get_embedding(f"embed this email thread, focus on the meaning of the conversation: {thread_markdown}")

    # 4. Determine the Qdrant point ID of the source thread to exclude it from search results
    source_point_id = generate_qdrant_point_id(source_thread.thread_id)

    # 5. Perform initial vector search in the 'email_threads' collection (get more results for reranking)
    initial_search_k = max(top_k * 3, 10)  # Get 3x more results for reranking
    similar_hits = search_by_vector(
        collection_name="email_threads",
        query_vector=source_embedding,
        top_k=initial_search_k,
        exclude_ids=[source_point_id],
    )

    if not similar_hits:
        return "No similar threads found."

    # 6. Prepare documents for reranking using thread_markdown from vector search results
    thread_contents = []
    thread_metadata = []
    
    for hit in similar_hits:
        thread_markdown_content = hit.get("thread_markdown", "")
        
        if thread_markdown_content:
            thread_contents.append(thread_markdown_content)
            # Store the hit payload as metadata for formatting
            thread_metadata.append(hit)

    if not thread_contents:
        return "No similar threads found."

    # 7. Use reranker to improve ordering based on relevance
    try:
        reranked_results = rerank_documents(
            query="Find similar threads to the following email and contain content that is relevant to the following email: " + source_thread.markdown,
            documents=thread_contents,
            top_k=top_k
        )
    except Exception as e:
        logger.warning(f"Reranking failed, falling back to vector search results: {e}")
        # Fallback to original vector search results
        reranked_results = [{"index": i} for i in range(min(len(thread_contents), top_k or 3))]

    # 8. Format threads using the reranked order - use the markdown directly
    similar_threads_formatted = []
    
    for result in reranked_results:
        index = result["index"]
        if index < len(thread_metadata):
            hit_metadata = thread_metadata[index]
            
            # Use the thread markdown directly since it's already well-formatted
            thread_markdown_content = hit_metadata.get("thread_markdown", "")
            if thread_markdown_content:
                similar_threads_formatted.append(thread_markdown_content)

    if not similar_threads_formatted:
        return "No similar threads found."

    # 9. Combine the reranked threads into a single markdown string
    header = f"Here are {len(similar_threads_formatted)} similar threads, ordered by relevance:"
    full_markdown_output = header + "\n\n"

    for i, thread_markdown in enumerate(similar_threads_formatted):
        full_markdown_output += thread_markdown
        # Add a separator between threads, but not after the last one
        if i < len(similar_threads_formatted) - 1:
            full_markdown_output += "\n\n---\n\n"

    return full_markdown_output

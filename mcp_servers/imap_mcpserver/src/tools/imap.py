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
from ..imap_client.client import get_message_by_id, get_complete_thread, draft_reply as client_draft_reply
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

# The following tools are not directly related to IMAP but are often used in the same context.
# They can be moved to a different service/tool file later if needed.

@mcp_builder.tool()
async def find_similar_threads(messageId: str, top_k: Optional[int] = 5) -> Dict[str, Any]:
    """
    Finds email threads with similar content to the thread of a given email ID.
    Uses vector search followed by reranking for improved relevance.
    """
    # 1. Get the original message using the client
    original_message = await get_message_by_id(messageId)
    if not original_message:
        return {"error": f"Could not find email with messageId: {messageId}"}

    # 2. Get the complete thread using the client
    source_thread = await get_complete_thread(original_message)
    if not source_thread:
        return {"error": f"Could not retrieve the thread for email ID {messageId} to find similar conversations."}

    # 3. Use the thread's markdown property for embedding - it's already formatted and cleaned
    thread_markdown = source_thread.markdown
    if not thread_markdown.strip():
        return {"error": f"Could not extract any content from the source thread of email {messageId}."}
    
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
        return {"similar_threads": [], "llm_instructions": "No similar threads found."}

    # 6. Prepare documents for reranking using thread_markdown from vector search results
    thread_contents = []
    thread_metadata = []
    
    for hit in similar_hits:
        thread_markdown = hit.get("thread_markdown", "")
        
        if thread_markdown:
            thread_contents.append(thread_markdown)
            # Store the hit payload as metadata for formatting
            thread_metadata.append(hit)

    if not thread_contents:
        return {"similar_threads": [], "llm_instructions": "No valid thread content found for reranking."}

    # 7. Use reranker to improve ordering based on relevance
    try:
        reranked_results = rerank_documents(
            query="Find similar threads to the following email and contain content that is relevant to the following email: " + cleaned_thread_content,
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
            thread_markdown = hit_metadata.get("thread_markdown", "")
            if thread_markdown:
                similar_threads_formatted.append(thread_markdown)

    return {
        "similar_threads": similar_threads_formatted,
        "llm_instructions": "These are full conversation threads that are semantically similar to the original email's thread, ordered by relevance using AI reranking."
    }

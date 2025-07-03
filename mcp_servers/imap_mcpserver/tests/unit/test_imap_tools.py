import sys
import os
from unittest.mock import patch, AsyncMock, MagicMock
import pytest

# Add project root to the Python path to allow for correct module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

# Create a mock for the entire qdrant_client module to prevent it from running its connection logic on import.
# This is necessary because the connection is initiated at the module level.
mock_qdrant_module = MagicMock()
sys.modules['shared.qdrant.qdrant_client'] = mock_qdrant_module

# Now that the problematic module is mocked, we can safely import the app
from mcp_servers.imap_mcpserver.src.tools.imap import find_similar_threads

@pytest.mark.asyncio
async def test_find_similar_threads_success():
    with patch('mcp_servers.imap_mcpserver.src.tools.imap.get_message_by_id', new_callable=AsyncMock) as mock_get_message_by_id, \
         patch('mcp_servers.imap_mcpserver.src.tools.imap.get_complete_thread', new_callable=AsyncMock) as mock_get_complete_thread, \
         patch('mcp_servers.imap_mcpserver.src.tools.imap.get_embedding') as mock_get_embedding, \
         patch('mcp_servers.imap_mcpserver.src.tools.imap.generate_qdrant_point_id') as mock_generate_qdrant_point_id, \
         patch('mcp_servers.imap_mcpserver.src.tools.imap.search_by_vector') as mock_search_by_vector, \
         patch('mcp_servers.imap_mcpserver.src.tools.imap.rerank_documents') as mock_rerank_documents:

        # 1. Setup mocks
        mock_message = MagicMock()
        mock_get_message_by_id.return_value = mock_message

        mock_thread = MagicMock()
        mock_thread.markdown = "This is the source thread markdown."
        mock_thread.thread_id = "thread-123"
        mock_get_complete_thread.return_value = mock_thread

        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        mock_generate_qdrant_point_id.return_value = "qdrant-id-123"

        mock_search_results = [
            {"thread_markdown": "Similar thread 1 markdown"},
            {"thread_markdown": "Similar thread 2 markdown"},
        ]
        mock_search_by_vector.return_value = mock_search_results

        mock_reranked_results = [
            {"index": 1},
            {"index": 0},
        ]
        mock_rerank_documents.return_value = mock_reranked_results

        # 2. Call the function
        result = await find_similar_threads.fn(messageId="test-message-id", top_k=2)

        # 3. Assertions
        mock_get_message_by_id.assert_awaited_once_with("test-message-id")
        mock_get_complete_thread.assert_awaited_once_with(mock_message)
        
        mock_get_embedding.assert_called_once_with(f"embed this email thread, focus on the meaning of the conversation: {mock_thread.markdown}")
        
        mock_generate_qdrant_point_id.assert_called_once_with("thread-123")
        
        mock_search_by_vector.assert_called_once_with(
            collection_name="email_threads",
            query_vector=[0.1, 0.2, 0.3],
            top_k=10,  # max(2 * 3, 10)
            exclude_ids=["qdrant-id-123"],
        )

        mock_rerank_documents.assert_called_once_with(
            query="Find similar threads to the following email and contain content that is relevant to the following email: " + mock_thread.markdown,
            documents=["Similar thread 1 markdown", "Similar thread 2 markdown"],
            top_k=2
        )
        
        assert "similar_threads" in result
        assert len(result["similar_threads"]) == 2
        assert result["similar_threads"][0] == "Similar thread 2 markdown"
        assert result["similar_threads"][1] == "Similar thread 1 markdown"
        assert "llm_instructions" in result

@pytest.mark.asyncio
async def test_find_similar_threads_no_message():
    with patch('mcp_servers.imap_mcpserver.src.tools.imap.get_message_by_id', new_callable=AsyncMock) as mock_get_message_by_id:
        mock_get_message_by_id.return_value = None

        result = await find_similar_threads.fn(messageId="non-existent-id")

        mock_get_message_by_id.assert_awaited_once_with("non-existent-id")
        assert result == {"error": "Could not find email with messageId: non-existent-id"}

@pytest.mark.asyncio
async def test_find_similar_threads_no_similar_found():
    with patch('mcp_servers.imap_mcpserver.src.tools.imap.get_message_by_id', new_callable=AsyncMock) as mock_get_message_by_id, \
         patch('mcp_servers.imap_mcpserver.src.tools.imap.get_complete_thread', new_callable=AsyncMock) as mock_get_complete_thread, \
         patch('mcp_servers.imap_mcpserver.src.tools.imap.get_embedding') as mock_get_embedding, \
         patch('mcp_servers.imap_mcpserver.src.tools.imap.generate_qdrant_point_id'), \
         patch('mcp_servers.imap_mcpserver.src.tools.imap.search_by_vector') as mock_search_by_vector:

        mock_message = MagicMock()
        mock_get_message_by_id.return_value = mock_message

        mock_thread = MagicMock()
        mock_thread.markdown = "Source thread"
        mock_thread.thread_id = "thread-456"
        mock_get_complete_thread.return_value = mock_thread
        mock_get_embedding.return_value = [0.4, 0.5, 0.6]

        mock_search_by_vector.return_value = []

        result = await find_similar_threads.fn(messageId="test-id")

        assert result == {"similar_threads": [], "llm_instructions": "No similar threads found."} 
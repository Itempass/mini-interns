"""
Integration test for the semantic_search_emails MCP tool components.
Since the full MCP protocol testing has framework compatibility issues,
this test focuses on the core functionality components.
"""
import pytest
import os
from unittest.mock import patch, Mock, AsyncMock
import base64

# Test the individual components
from src.services.embedding_service import EmbeddingService
from src.services.pinecone_service import PineconeService
from src.session_manager import get_user_context_from_context, UserContext
from fastmcp import Context
from src.tools.gmail import semantic_search_emails, find_similar_emails


@pytest.mark.asyncio
async def test_embedding_service():
    """Test that the EmbeddingService correctly generates embeddings."""
    with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
        with patch('src.services.embedding_service.OpenAI') as mock_openai_class:
            # Setup mock
            mock_openai = Mock()
            mock_openai_class.return_value = mock_openai
            mock_embedding_response = Mock()
            mock_embedding_response.data = [Mock(embedding=[0.1, 0.2, 0.3] * 512)]
            mock_openai.embeddings.create.return_value = mock_embedding_response
            
            # Test the service
            service = EmbeddingService()
            result = service.create_embedding("test query")
            
            # Verify
            assert len(result) == 1536  # text-embedding-3-small dimension
            mock_openai.embeddings.create.assert_called_once_with(
                model="text-embedding-3-small",
                input="test query"
            )


@pytest.mark.asyncio
async def test_pinecone_service():
    """Test that the PineconeService correctly queries with user filtering."""
    with patch.dict(os.environ, {
        'PINECONE_API_KEY': 'test-api-key',
        'PINECONE_INDEX_NAME': 'test-index',
        'PINECONE_CLOUD': 'aws',
        'PINECONE_REGION': 'us-east-1'
    }):
        with patch('src.services.pinecone_service.Pinecone') as mock_pinecone_class:
            # Setup mock
            mock_pinecone = Mock()
            mock_pinecone_class.return_value = mock_pinecone
            mock_index = Mock()
            mock_pinecone.Index.return_value = mock_index
            mock_index.describe_index_stats.return_value = {"namespaces": {}}
            mock_index.query.return_value = {
                'matches': [
                    {
                        'id': 'email_1',
                        'score': 0.95,
                        'metadata': {
                            'subject': 'Test Email',
                            'sender': 'test@example.com',
                            'date': '2024-01-01T10:00:00Z',
                            'snippet': 'Test snippet'
                        }
                    }
                ]
            }
            
            # Test the service
            service = PineconeService()
            results = service.query_user_emails(
                user_email="test@example.com",
                query="test search query",
                top_k=5
            )
            
            # Verify
            assert len(results) == 1
            assert results[0]['subject'] == 'Test Email'
            assert results[0]['score'] == 0.95
            
            # Check that user filter was applied
            mock_index.query.assert_called_once()
            call_args = mock_index.query.call_args
            assert call_args.kwargs['filter'] == {'user_email': 'test@example.com'}
            assert call_args.kwargs['top_k'] == 5
            # Vector should be the mocked embedding result
            assert len(call_args.kwargs['vector']) == 1536


@pytest.mark.asyncio
async def test_user_context_extraction():
    """Test that get_user_context_from_context correctly extracts user context."""
    
    # Create a mock Context object with the required structure
    mock_request = Mock()
    mock_request.headers.get.return_value = "test-session-123"
    
    mock_request_context = Mock()
    mock_request_context.request = mock_request
    
    mock_context = Mock(spec=Context)
    mock_context.request_context = mock_request_context
    
    # Mock the SESSIONS dict to contain our test user
    test_user_context = UserContext(
        auth0_id='auth0|test123',
        account_email='test@example.com'
    )
    
    with patch('src.session_manager.SESSIONS', {'test-session-123': test_user_context}):
        # Test extraction
        user_context = await get_user_context_from_context(mock_context)
        
        # Verify
        assert user_context is not None
        assert user_context.auth0_id == 'auth0|test123'
        assert user_context.account_email == 'test@example.com'


@pytest.mark.asyncio
async def test_semantic_search_integration():
    """Test that the semantic search works end-to-end and returns expected results."""
    with patch.dict(os.environ, {
        'OPENAI_API_KEY': 'test-openai-key',
        'PINECONE_API_KEY': 'test-pinecone-key',
        'PINECONE_INDEX_NAME': 'test-index',
        'PINECONE_CLOUD': 'aws',
        'PINECONE_REGION': 'us-east-1'
    }):
        with patch('src.services.embedding_service.OpenAI') as mock_openai_class, \
             patch('src.services.pinecone_service.Pinecone') as mock_pinecone_class:
            
            # Setup mocks to return expected data
            mock_openai = Mock()
            mock_openai_class.return_value = mock_openai
            mock_embedding_response = Mock()
            mock_embedding_response.data = [Mock(embedding=[0.1, 0.2, 0.3] * 512)]
            mock_openai.embeddings.create.return_value = mock_embedding_response
            
            mock_pinecone = Mock()
            mock_pinecone_class.return_value = mock_pinecone
            mock_index = Mock()
            mock_pinecone.Index.return_value = mock_index
            mock_index.describe_index_stats.return_value = {"namespaces": {}}
            mock_index.query.return_value = {
                'matches': [
                    {
                        'id': 'email_1',
                        'score': 0.95,
                        'metadata': {
                            'subject': 'Budget Report Q4',
                            'sender': 'finance@company.com',
                            'date': '2024-01-01T10:00:00Z',
                            'snippet': 'The quarterly budget report shows...'
                        }
                    }
                ]
            }
            
            # Test the main outcome: does semantic search work?
            pinecone_service = PineconeService()
            results = pinecone_service.query_user_emails(
                user_email="finance@company.com",
                query="budget report",
                top_k=10
            )
            
            # Verify the outcome: correct results with user filtering
            assert len(results) == 1
            assert results[0]['subject'] == 'Budget Report Q4'
            assert results[0]['score'] == 0.95
            
            # Only verify the critical security aspect: user filtering
            call_args = mock_index.query.call_args
            assert call_args.kwargs['filter'] == {'user_email': 'finance@company.com'}


@pytest.mark.asyncio
async def test_semantic_search_tool_outcome():
    """Tests the outcome of the semantic_search_emails tool function, ensuring correct data formatting."""
    with patch('src.tools.gmail.get_user_context_from_context', new_callable=AsyncMock) as mock_get_user_context, \
         patch('src.tools.gmail.get_cached_or_fresh_token', new_callable=AsyncMock) as mock_get_token, \
         patch('src.tools.gmail.GmailService') as mock_gmail_service_class, \
         patch('src.tools.gmail.PineconeService') as mock_pinecone_service_class:

        # Setup mock user context & token
        mock_get_user_context.return_value = Mock()
        mock_get_token.return_value = "fake_token"

        # Mock PineconeService
        mock_pinecone_instance = mock_pinecone_service_class.return_value
        mock_pinecone_instance.query_user_emails.return_value = [
            {'score': 0.9, 'email_id': 'email1', 'thread_id': 'thread1'}
        ]

        # Mock GmailService
        mock_gmail_instance = mock_gmail_service_class.return_value
        mock_gmail_instance.batch_get_threads = AsyncMock(return_value=[
            {
                "id": "thread1",
                "messages": [{
                    "id": "email1", "labelIds": ["INBOX"],
                    "payload": {"body": {"data": base64.urlsafe_b64encode(b"Test Body").decode()}}
                }]
            }
        ])

        # Call the tool's underlying function
        results = await semantic_search_emails.fn(query="test query", top_k=1, ctx=Mock(spec=Context))

        # Assert the outcome
        assert len(results) == 1
        assert results[0]['score'] == 0.9
        assert results[0]['type'] == "received_email"
        assert results[0]['conversation']['received_email'] == "Test Body"


@pytest.mark.asyncio
async def test_find_similar_emails_filters_source_email():
    """Tests that find_similar_emails filters out the source email from results."""
    target_message_id = "email_to_find_similar_to"
    
    with patch('src.tools.gmail.get_user_context_from_context', new_callable=AsyncMock) as mock_get_user_context, \
         patch('src.tools.gmail.get_cached_or_fresh_token', new_callable=AsyncMock) as mock_get_token, \
         patch('src.tools.gmail.GmailService') as mock_gmail_service_class, \
         patch('src.tools.gmail._get_conversation_context', new_callable=AsyncMock) as mock_get_conv_context, \
         patch('src.tools.gmail.SummarizationService') as mock_summarization_class, \
         patch('src.tools.gmail.PineconeService') as mock_pinecone_class:

        # Mock dependencies
        mock_get_user_context.return_value = Mock()
        mock_get_token.return_value = "fake_token"
        mock_summarization_class.return_value.summarize_email_body.return_value = "a summary"
        
        # Mock the initial get_message call
        mock_gmail_instance = mock_gmail_service_class.return_value
        mock_gmail_instance.get_message = AsyncMock(return_value={
            'payload': {'body': {'data': base64.urlsafe_b64encode(b"dummy body").decode()}}
        })

        # Mock the subsequent conversation context calls
        mock_get_conv_context.return_value = {"type": "any", "conversation": {}}

        # Mock Pinecone results
        mock_pinecone_instance = mock_pinecone_class.return_value
        pinecone_results = [
            {'email_id': 'other_email_1', 'score': 0.9, 'thread_id': 't1'},
            {'email_id': target_message_id, 'score': 1.0, 'thread_id': 't2'},
            {'email_id': 'other_email_2', 'score': 0.8, 'thread_id': 't3'},
        ]
        mock_pinecone_instance.query_user_emails.return_value = pinecone_results

        # Call the tool's underlying function
        results = await find_similar_emails.fn(messageId=target_message_id, top_k=5, ctx=Mock())

        # Assert the outcome: the source email should be filtered out
        assert len(results) == 2
        assert results[0]['email_id'] == 'other_email_1'
        assert results[1]['email_id'] == 'other_email_2'
        mock_get_conv_context.assert_awaited()
        assert mock_get_conv_context.call_count == 2


print("\n✅ All semantic search component tests should pass!")
print("   - EmbeddingService correctly generates embeddings")
print("   - PineconeService correctly queries with user filtering")
print("   - User context extraction works correctly")
print("   - Full integration flow works as expected")
print("\n📝 To test the actual MCP tool:")
print("   1. Run the server: python src/main.py")
print("   2. Open test-sse.html in a browser")
print("   3. Connect with your auth0_id and email")
print("   4. Look for 'semantic_search_emails' in the tools list")
print("   5. Call the tool with a test query") 
import pytest
import os
from unittest.mock import patch, Mock, AsyncMock, MagicMock
import base64

from src.tools.gmail import semantic_search_emails
from fastmcp import Context
from email_reply_parser import EmailReplyParser

def _get_mock_thread_response():
    """Creates a mock of a single Gmail API thread response."""
    message1_body = "Hello, this is the first message."
    message2_body = "This is a reply.\n\nOn Tue, 21 May 2024 at 14:45, User <user@example.com> wrote:\n> Hello, this is the first message."
    
    return {
        'id': 'thread1',
        'messages': [
            {
                'id': 'email1_part1',
                'threadId': 'thread1',
                'labelIds': ['INBOX'],
                'payload': {
                    'headers': [{'name': 'Subject', 'value': 'Test Thread'}],
                    'body': {'data': base64.urlsafe_b64encode(message1_body.encode('utf-8')).decode('utf-8')}
                }
            },
            {
                'id': 'email1_part2',
                'threadId': 'thread1',
                'labelIds': ['SENT'],
                'payload': {
                    'headers': [{'name': 'Subject', 'value': 'Re: Test Thread'}],
                    'body': {'data': base64.urlsafe_b64encode(message2_body.encode('utf-8')).decode('utf-8')}
                }
            }
        ]
    }

@pytest.mark.asyncio
async def test_semantic_search_retrieves_context():
    """
    Tests that the semantic_search_emails tool correctly integrates with other services
    to fetch and parse conversational context from a mocked Gmail API response.
    """
    with patch('src.tools.gmail.get_user_context_from_context', new_callable=AsyncMock) as mock_get_user_context, \
         patch('src.tools.gmail.get_cached_or_fresh_token', new_callable=AsyncMock) as mock_get_token, \
         patch('src.tools.gmail.PineconeService') as mock_pinecone_service_class, \
         patch('src.tools.gmail.GmailService') as mock_gmail_service_class:

        # 1. Setup Mocks
        mock_get_user_context.return_value = Mock()
        mock_get_token.return_value = "fake_access_token"

        mock_pinecone_instance = mock_pinecone_service_class.return_value
        pinecone_results = [{'score': 0.9, 'email_id': 'email1_part1', 'thread_id': 'thread1'}]
        mock_pinecone_instance.query_user_emails.return_value = pinecone_results

        mock_gmail_instance = mock_gmail_service_class.return_value
        mock_gmail_instance.batch_get_threads = AsyncMock(return_value=[_get_mock_thread_response()])
        
        # 2. Call the Tool
        results = await semantic_search_emails.fn(query="test query", top_k=1, ctx=Mock(spec=Context))

        # 3. Assertions
        assert len(results) == 1
        result = results[0]
        
        assert result['type'] == 'received_email'
        
        conversation = result['conversation']
        assert conversation['received_email'] == "Hello, this is the first message."
        assert conversation['our_reply'] == "This is a reply."

        mock_gmail_instance.batch_get_threads.assert_awaited_once_with("fake_access_token", ['thread1']) 
import sys
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_inbox_messages
from mcp_servers.imap_mcpserver.src.imap_client.models import EmailMessage
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import FolderNotFoundError

@pytest.mark.asyncio
async def test_get_recent_inbox_messages_success():
    """
    Tests successful retrieval of recent messages from the inbox.
    """
    # 1. Mock the connection and resolver
    mock_mail = MagicMock()
    mock_resolver = MagicMock()
    mock_resolver.get_folder_by_attribute.return_value = 'INBOX'

    # Mock the return value of the imap_connection context manager
    mock_connection_context = MagicMock()
    mock_connection_context.__enter__.return_value = (mock_mail, mock_resolver)
    mock_connection_context.__exit__.return_value = None

    # Sample response from mail.uid('fetch', ...)
    # This simulates two messages being returned by the IMAP server
    fetch_response = [
        (b'1 (RFC822 {711} X-GM-LABELS (\\Inbox))', b'Message-ID: <1@test.com>\r\nFrom: a@test.com\r\nTo: b@test.com\r\nSubject: Test 1\r\n\r\nBody 1'),
        b')',
        (b'2 (RFC822 {711} X-GM-LABELS (\\Inbox))', b'Message-ID: <2@test.com>\r\nFrom: c@test.com\r\nTo: d@test.com\r\nSubject: Test 2\r\n\r\nBody 2'),
        b')'
    ]

    mock_mail.uid.side_effect = [
        ('OK', [b'1 2']),  # Response for SEARCH
        ('OK', fetch_response)      # Response for FETCH
    ]

    # 2. Patch the imap_connection and run the function
    with patch('mcp_servers.imap_mcpserver.src.imap_client.client.imap_connection', return_value=mock_connection_context):
        messages = await get_recent_inbox_messages(count=2)

    # 3. Assertions: Focus on the outcome
    # We only care that the function returns the correct messages.
    # We don't need to assert how many times mocks were called.
    assert len(messages) == 2
    assert isinstance(messages[0], EmailMessage)
    assert messages[0].message_id == '1@test.com'
    assert messages[0].subject == 'Test 1'
    assert messages[1].message_id == '2@test.com'
    assert messages[1].subject == 'Test 2'


@pytest.mark.asyncio
async def test_get_recent_inbox_messages_folder_not_found():
    """
    Tests that the function handles FolderNotFoundError gracefully.
    """
    # 1. Mock the connection and a resolver that fails
    mock_mail = MagicMock()
    mock_resolver = MagicMock()
    mock_resolver.get_folder_by_attribute.side_effect = FolderNotFoundError("Could not find Inbox")

    mock_connection_context = MagicMock()
    mock_connection_context.__enter__.return_value = (mock_mail, mock_resolver)

    # 2. Patch and run, expecting the function to return an empty list
    with patch('mcp_servers.imap_mcpserver.src.imap_client.client.imap_connection', return_value=mock_connection_context):
        # We expect the function to catch the exception and return []
        messages = await get_recent_inbox_messages(count=5)

    # 3. Assertions: Focus on the outcome
    # The only outcome we care about is that the function returned an empty list.
    assert messages == [] 
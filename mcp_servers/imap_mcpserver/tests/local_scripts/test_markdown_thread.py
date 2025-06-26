#!/usr/bin/env python3

import asyncio
import sys
import os
from dotenv import load_dotenv
from contextlib import contextmanager
from unittest.mock import patch

# Add project root to sys.path to allow for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

# Load environment variables from .env file
load_dotenv(override=True)

from mcp_servers.imap_mcpserver.src.imap_client.client import get_message_by_id, get_complete_thread

TEST_MESSAGE_ID = "CAPajfh+gpXutnYeOCPjDXamDtbLoUBN1+sOycrCPjgV0YLXxMw@mail.gmail.com"

# --- Test Setup ---
redis_patcher = patch('shared.redis.redis_client.get_redis_client', side_effect=ConnectionRefusedError("Redis is not available for this test"))

@contextmanager
def patch_connection_manager():
    """Patches the client's imap_connection to use a test connection manager."""
    from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import IMAPConnectionManager
    
    required_vars = ["TEST_IMAP_USER", "TEST_IMAP_PASSWORD", "TEST_IMAP_SERVER"]
    if not all(os.getenv(var) for var in required_vars):
        raise EnvironmentError("Missing required test variables in .env file: TEST_IMAP_USER, TEST_IMAP_PASSWORD, TEST_IMAP_SERVER")

    test_conn_manager = IMAPConnectionManager(
        server=os.environ["TEST_IMAP_SERVER"],
        username=os.environ["TEST_IMAP_USER"],
        password=os.environ["TEST_IMAP_PASSWORD"],
    )
    print(f"  Testing with connection manager for user: {test_conn_manager.username}")
    
    with patch('mcp_servers.imap_mcpserver.src.imap_client.client.imap_connection', test_conn_manager.connect):
        yield

async def main():
    print(f"Testing EmailThread.markdown property for message ID: {TEST_MESSAGE_ID}")
    
    with patch_connection_manager():
        # Get a specific message to test with
        print(f"\n1. Getting message by ID: {TEST_MESSAGE_ID}")
        source_message = await get_message_by_id(TEST_MESSAGE_ID)
        
        if not source_message:
            print(f"❌ Message with ID {TEST_MESSAGE_ID} not found.")
            return
        
        print(f"Found message: {source_message.subject}")
        
        # Get complete thread for the message
        print(f"\n2. Getting complete thread for: {source_message.subject}")
        thread = await get_complete_thread(source_message)
        
        if not thread:
            print("❌ No thread found")
            return
        
        print(f"✅ Thread found with {thread.message_count} messages")
        
        # Test the markdown property
        print(f"\n3. Generating markdown for thread...")
        markdown_content = thread.markdown
        
        # Show first 500 characters
        print(f"Markdown content (first 500 chars):")
        print("=" * 50)
        print(markdown_content)
        print("=" * 50)
        
        # Optionally save to file for inspection
        output_file = "thread_markdown_output.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"\n✅ Complete markdown saved to: {output_file}")
        print(f"Thread has {thread.message_count} messages formatted as markdown")

if __name__ == "__main__":
    redis_patcher.start()
    try:
        asyncio.run(main())
    finally:
        redis_patcher.stop() 
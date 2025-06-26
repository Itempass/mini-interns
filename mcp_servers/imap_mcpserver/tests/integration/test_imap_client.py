#!/usr/bin/env python3

import os
import sys
import asyncio
import logging
import time
from contextlib import contextmanager
from unittest.mock import patch
from dotenv import load_dotenv

# Add project root to sys.path to allow for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, project_root)

# Load environment variables from .env file
load_dotenv(override=True)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

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
    print(f"  Testing with connection manager: {test_conn_manager.username}")
    
    # Patch the imap_connection context manager used by most client functions
    with patch('mcp_servers.imap_mcpserver.src.imap_client.client.imap_connection', test_conn_manager.connect):
        # Also patch the default manager used by the bulk threading module
        with patch('mcp_servers.imap_mcpserver.src.imap_client.internals.bulk_threading.get_default_connection_manager', return_value=test_conn_manager):
            yield

# --- Test Cases ---
async def test_get_recent_inbox_message_ids():
    from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_inbox_message_ids
    with patch_connection_manager():
        try:
            ids = await get_recent_inbox_message_ids(count=5)
            assert isinstance(ids, list)
            logging.info(f"  ✓ Found {len(ids)} message IDs.")
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            assert False, "Test failed due to exception"

async def test_get_recent_inbox_messages():
    from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_inbox_messages
    with patch_connection_manager():
        try:
            messages = await get_recent_inbox_messages(count=5)
            assert isinstance(messages, list)
            logging.info(f"  ✓ Fetched {len(messages)} messages.")
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            assert False, "Test failed due to exception"

async def test_get_recent_sent_messages():
    from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_sent_messages
    with patch_connection_manager():
        try:
            messages = await get_recent_sent_messages(count=5)
            assert isinstance(messages, list)
            logging.info(f"  ✓ Fetched {len(messages)} sent messages.")
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            assert False, "Test failed due to exception"

async def test_get_message_by_id():
    from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_inbox_message_ids, get_message_by_id
    with patch_connection_manager():
        ids = await get_recent_inbox_message_ids(count=1)
        if not ids:
            logging.warning("  ⚠️ No message IDs found - skipping message by ID test")
            return
        
        message_id = ids[0]
        try:
            message = await get_message_by_id(message_id)
            assert message is not None
            logging.info(f"  ✓ Fetched message by ID {message.message_id} successfully.")
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            assert False, "Test failed due to exception"

async def test_get_complete_thread():
    from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_inbox_messages, get_complete_thread
    with patch_connection_manager():
        messages = await get_recent_inbox_messages(count=1)
        if not messages:
            logging.warning("  ⚠️ No messages in inbox to test with - skipping thread test")
            return
            
        source_message = messages[0]
        try:
            thread = await get_complete_thread(source_message)
            assert thread is not None
            logging.info(f"  ✓ Fetched thread for message {source_message.uid} successfully.")
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            assert False, "Test failed due to exception"

async def test_draft_reply():
    from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_inbox_messages, draft_reply
    with patch_connection_manager():
        messages = await get_recent_inbox_messages(count=1)
        if not messages:
            logging.warning("  ⚠️ No messages in inbox to test with - skipping draft reply test")
            return

        original_message = messages[0]
        try:
            result = await draft_reply(original_message, "This is a test reply from an integration test.")
            assert result.get("success") is True
            logging.info(f"  ✓ Drafted reply to message {original_message.uid} successfully.")
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            assert False, "Test failed due to exception"

async def test_get_recent_threads_bulk():
    from mcp_servers.imap_mcpserver.src.imap_client.client import get_recent_threads_bulk
    with patch_connection_manager():
        try:
            start_time = time.time()
            threads, timing_info = await get_recent_threads_bulk(target_thread_count=10)
            end_time = time.time()
            
            assert isinstance(threads, list)
            assert len(threads) <= 10
            
            duration = end_time - start_time
            breakdown = f"sent({timing_info.get('fetch_sent_time', 0):.2f}s) + discovery({timing_info.get('thread_discovery_time', 0):.2f}s) + fetch({timing_info.get('bulk_fetch_time', 0):.2f}s)"
            logging.info(f"  ✓ Bulk fetch: {len(threads)} threads in {duration:.2f}s")
            logging.info(f"    Breakdown: {breakdown}")
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            assert False, "Test failed due to exception"


if __name__ == "__main__":
    redis_patcher.start()
    try:
        async def run_tests():
            print("🧪 Testing IMAP Client Integration...")
            
            tests_to_run = [
                ("get_recent_inbox_message_ids", test_get_recent_inbox_message_ids),
                ("get_recent_inbox_messages", test_get_recent_inbox_messages),
                ("get_recent_sent_messages", test_get_recent_sent_messages),
                ("get_message_by_id", test_get_message_by_id),
                ("get_complete_thread", test_get_complete_thread),
                ("draft_reply", test_draft_reply),
                ("get_recent_threads_bulk", test_get_recent_threads_bulk),
            ]

            all_passed = True
            for name, test_func in tests_to_run:
                print(f"\n--- Testing {name} ---")
                try:
                    await test_func()
                    print("✅ PASSED")
                except AssertionError:
                    all_passed = False
                    print("❌ FAILED")

            print("\n" + ("🎉 All integration tests passed!" if all_passed else "🔥 Some tests failed."))

        asyncio.run(run_tests())
    finally:
        redis_patcher.stop() 
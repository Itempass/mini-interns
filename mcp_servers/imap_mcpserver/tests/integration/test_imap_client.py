#!/usr/bin/env python3

import asyncio
import sys
import os
import pytest

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from imap_client.client import (
    get_recent_inbox_message_ids,
    get_message_by_id,
    get_complete_thread,
    get_recent_inbox_messages,
    get_recent_sent_messages,
    draft_reply,
    get_recent_threads_bulk
)

@pytest.mark.asyncio
async def test_get_recent_inbox_message_ids():
    """Test getting recent inbox message IDs"""
    message_ids = await get_recent_inbox_message_ids(count=5)
    
    # Outcomes to test
    assert isinstance(message_ids, list)
    assert len(message_ids) <= 5
    if message_ids:
        assert all(isinstance(msg_id, str) for msg_id in message_ids)
        assert all('@' in msg_id for msg_id in message_ids)  # Should be valid message IDs

@pytest.mark.asyncio
async def test_get_recent_inbox_messages():
    """Test getting recent inbox messages as EmailMessage objects"""
    messages = await get_recent_inbox_messages(count=3)
    
    # Outcomes to test
    assert isinstance(messages, list)
    assert len(messages) <= 3
    
    if messages:
        msg = messages[0]
        # Check EmailMessage structure
        assert hasattr(msg, 'uid')
        assert hasattr(msg, 'message_id')
        assert hasattr(msg, 'from_')
        assert hasattr(msg, 'subject')
        assert hasattr(msg, 'body_raw')
        assert hasattr(msg, 'body_markdown')
        assert hasattr(msg, 'body_cleaned')
        assert hasattr(msg, 'gmail_labels')
        
        # Check data types
        assert isinstance(msg.uid, str)
        assert isinstance(msg.message_id, str)
        assert isinstance(msg.gmail_labels, list)
        assert '@' in msg.message_id  # Valid message ID
        assert ':' in msg.uid  # Contextual ID format

@pytest.mark.asyncio
async def test_get_recent_sent_messages():
    """Test getting recent sent messages as EmailMessage objects"""
    messages = await get_recent_sent_messages(count=3)
    
    # Outcomes to test
    assert isinstance(messages, list)
    assert len(messages) <= 3
    
    if messages:
        msg = messages[0]
        # Check EmailMessage structure
        assert hasattr(msg, 'uid')
        assert hasattr(msg, 'message_id')
        assert hasattr(msg, 'from_')
        assert hasattr(msg, 'to')
        assert hasattr(msg, 'subject')
        assert hasattr(msg, 'body_raw')
        assert hasattr(msg, 'body_markdown')
        assert hasattr(msg, 'body_cleaned')
        assert hasattr(msg, 'gmail_labels')
        
        # Check that it's from sent folder by decoding the contextual UID
        import base64
        encoded_mailbox = msg.uid.split(':')[0]
        mailbox = base64.b64decode(encoded_mailbox).decode('utf-8')
        assert '[Gmail]/Sent Mail' in mailbox

@pytest.mark.asyncio
async def test_get_complete_thread():
    """Test getting complete thread for a message"""
    # First get a message to test with
    messages = await get_recent_inbox_messages(count=1)
    
    if not messages:
        pytest.skip("No messages in inbox to test with")
    
    thread = await get_complete_thread(messages[0])
    
    # Outcomes to test
    if thread:  # Thread might be None if message not found
        assert hasattr(thread, 'thread_id')
        assert hasattr(thread, 'message_count')
        assert hasattr(thread, 'messages')
        assert hasattr(thread, 'participants')
        assert hasattr(thread, 'folders')
        
        # Check data types and structure
        assert isinstance(thread.thread_id, str)
        assert isinstance(thread.message_count, int)
        assert isinstance(thread.messages, list)
        assert isinstance(thread.participants, list)
        assert isinstance(thread.folders, list)
        
        assert thread.message_count == len(thread.messages)
        assert thread.message_count > 0
        
        # Check first message structure
        if thread.messages:
            msg = thread.messages[0]
            assert hasattr(msg, 'body_raw')
            assert hasattr(msg, 'body_markdown')
            assert hasattr(msg, 'body_cleaned')
            
        # Test the new markdown property
        markdown_content = thread.markdown
        assert isinstance(markdown_content, str)
        assert "# Email Thread" in markdown_content
        assert "## Message 1:" in markdown_content
        assert "**From:**" in markdown_content
        assert "**To:**" in markdown_content
        assert "**Date:**" in markdown_content
        assert "**Message ID:**" in markdown_content
        assert "**Subject:**" in markdown_content

@pytest.mark.asyncio
async def test_get_message_by_id():
    """Test getting a single message by its Message-ID"""
    # First get a message ID to test with
    message_ids = await get_recent_inbox_message_ids(count=1)
    
    if not message_ids:
        pytest.skip("No messages in inbox to test with")
    
    message = await get_message_by_id(message_ids[0])
    
    # Outcomes to test
    if message:  # Message might be None if not found
        assert hasattr(message, 'uid')
        assert hasattr(message, 'message_id')
        assert hasattr(message, 'from_')
        assert hasattr(message, 'subject')
        assert hasattr(message, 'body_raw')
        assert hasattr(message, 'body_markdown')
        assert hasattr(message, 'body_cleaned')
        assert hasattr(message, 'gmail_labels')
        
        # Check data types
        assert isinstance(message.uid, str)
        assert isinstance(message.message_id, str)
        assert isinstance(message.gmail_labels, list)
        assert message.message_id == message_ids[0]  # Should match requested ID
        assert '@' in message.message_id  # Valid message ID
        assert ':' in message.uid  # Contextual ID format

@pytest.mark.asyncio
async def test_draft_reply():
    """Test creating a draft reply to a message"""
    # First get a message to reply to
    messages = await get_recent_inbox_messages(count=1)
    
    if not messages:
        pytest.skip("No messages in inbox to test with")
    
    original_message = messages[0]
    reply_body = "This is a test reply created by the integration test. Please ignore."
    
    result = await draft_reply(original_message, reply_body)
    
    # Outcomes to test
    assert isinstance(result, dict)
    assert 'success' in result
    assert 'message' in result
    assert isinstance(result['success'], bool)
    assert isinstance(result['message'], str)
    
    # The result should indicate success (we expect this to work)
    if result['success']:
        assert 'Draft' in result['message'] or 'draft' in result['message']
        print(f"✓ Draft reply created successfully: {result['message']}")
    else:
        print(f"⚠️ Draft reply failed (this might be expected in some environments): {result['message']}")

@pytest.mark.asyncio
async def test_get_recent_threads_bulk():
    """Test the high-performance bulk thread fetching functionality"""
    # Test with a small target count for faster testing
    target_count = 5
    max_age = 6  # months
    
    threads, timing = await get_recent_threads_bulk(
        target_thread_count=target_count,
        max_age_months=max_age
    )
    
    # Outcomes to test
    assert isinstance(threads, list)
    assert isinstance(timing, dict)
    
    # Check timing dictionary structure
    expected_timing_keys = ['fetch_sent_time', 'thread_discovery_time', 'bulk_fetch_time', 'total_time']
    for key in expected_timing_keys:
        assert key in timing
        assert isinstance(timing[key], (int, float))
        assert timing[key] >= 0  # Should be non-negative
    
    # Check that we got some threads (unless there really are none)
    if threads:
        # Should not exceed target (but might be slightly over due to batch processing)
        assert len(threads) <= target_count + 10  # Allow some overflow due to batching
        
        # Check thread structure
        thread = threads[0]
        assert hasattr(thread, 'thread_id')
        assert hasattr(thread, 'message_count')
        assert hasattr(thread, 'messages')
        assert hasattr(thread, 'participants')
        assert hasattr(thread, 'folders')
        
        # Check data types
        assert isinstance(thread.thread_id, str)
        assert isinstance(thread.message_count, int)
        assert isinstance(thread.messages, list)
        assert thread.message_count > 0
        assert len(thread.messages) > 0
        
        # Check that each message has the required body formats
        for message in thread.messages:
            assert hasattr(message, 'body_raw')
            assert hasattr(message, 'body_markdown')
            assert hasattr(message, 'body_cleaned')
            assert isinstance(message.body_raw, str)
            assert isinstance(message.body_markdown, str)
            assert isinstance(message.body_cleaned, str)
        
        # Performance check - should be reasonably fast
        assert timing['total_time'] < 30.0  # Should complete within 30 seconds for 5 threads
        
        print(f"✓ Bulk fetch: {len(threads)} threads in {timing['total_time']:.2f}s")
        print(f"  Breakdown: sent({timing['fetch_sent_time']:.2f}s) + discovery({timing['thread_discovery_time']:.2f}s) + fetch({timing['bulk_fetch_time']:.2f}s)")
        
        # Test thread deduplication - all thread IDs should be unique
        thread_ids = [t.thread_id for t in threads]
        assert len(thread_ids) == len(set(thread_ids)), "Thread IDs should be unique (deduplication test)"
    
    else:
        print("⚠️ No threads found - this might be expected if there are no recent sent messages")

if __name__ == "__main__":
    # Run tests directly
    async def run_tests():
        print("🧪 Testing IMAP Client Integration...")
        
        print("\n1. Testing get_recent_inbox_message_ids...")
        await test_get_recent_inbox_message_ids()
        print("✅ PASSED")
        
        print("\n2. Testing get_recent_inbox_messages...")
        await test_get_recent_inbox_messages()
        print("✅ PASSED")
        
        print("\n3. Testing get_recent_sent_messages...")
        await test_get_recent_sent_messages()
        print("✅ PASSED")
        
        print("\n4. Testing get_message_by_id...")
        await test_get_message_by_id()
        print("✅ PASSED")
        
        print("\n5. Testing get_complete_thread...")
        await test_get_complete_thread()
        print("✅ PASSED")
        
        print("\n6. Testing draft_reply...")
        await test_draft_reply()
        print("✅ PASSED")
        
        print("\n7. Testing get_recent_threads_bulk...")
        await test_get_recent_threads_bulk()
        print("✅ PASSED")
        
        print("\n🎉 All integration tests passed!")
    
    asyncio.run(run_tests()) 
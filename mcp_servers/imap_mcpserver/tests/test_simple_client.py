#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from imap_client.client import get_recent_inbox_message_ids, get_complete_thread

async def main():
    print("Testing simple IMAP client...")
    
    # Test 1: Get recent message IDs
    print("\n1. Getting recent inbox message IDs...")
    message_ids = await get_recent_inbox_message_ids(count=5)
    print(f"Found {len(message_ids)} recent messages:")
    for i, msg_id in enumerate(message_ids, 1):
        print(f"  {i}. {msg_id}")
    
    if message_ids:
        # Test 2: Get complete thread for first message
        print(f"\n2. Getting complete thread for: {message_ids[0]}")
        thread = await get_complete_thread(message_ids[0])
        
        if thread:
            print(f"✅ Thread found!")
            print(f"   Message ID: {thread.messages[0].message_id}")
            print(f"   Thread ID: {thread.thread_id}")
            print(f"   Messages: {thread.message_count}")
            print(f"   Subject: {thread.subject}")
            print(f"   Participants: {thread.participants}")
            print(f"   Folders: {thread.folders}")
            
            print(f"\n   First message:")
            first_msg = thread.messages[0]
            print(f"     From: {first_msg.from_}")
            print(f"     To: {first_msg.to}")
            print(f"     Labels: {first_msg.gmail_labels}")
            print(f"     Body: {first_msg.body[:100]}...")
        else:
            print("❌ No thread found")
    else:
        print("❌ No messages found in inbox")

if __name__ == "__main__":
    asyncio.run(main()) 
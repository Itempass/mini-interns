#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from imap_client.client import get_complete_thread

async def main():
    # The Message-ID from the Google OAuth verification email
    message_id = "000000000000d68c0e0637e4a5e0@google.com"
    
    print(f"Getting thread for Message-ID: {message_id}")
    
    thread = await get_complete_thread(message_id)
    
    if thread:
        print(f"\n✅ Thread found with {len(thread.messages)} messages!")
        print(f"Thread ID: {thread.thread_id}")
        print(f"Participants: {thread.participants}")
        print(f"Folders: {thread.folders}")
        
        print(f"\n📧 Individual Messages:")
        for i, message in enumerate(thread.messages, 1):
            print(f"\n--- Message {i} ---")
            print(f"From: {message.from_}")
            print(f"To: {message.to}")
            if message.cc:
                print(f"CC: {message.cc}")
            print(f"Subject: {message.subject}")
            print(f"Date: {message.date}")
            print(f"Labels: {message.gmail_labels}")
            print(f"Body (Raw): {message.body_raw}")
            print(f"Body (Markdown): {message.body_markdown}...")
            print(f"Body (Cleaned): {message.body_cleaned}...")
            print(f"UID: {message.uid}")
            print(f"Message ID: {message.message_id}")
    else:
        print("❌ Thread not found")

if __name__ == "__main__":
    asyncio.run(main()) 
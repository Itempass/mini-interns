#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from imap_client.client import get_recent_inbox_messages, get_complete_thread

async def main():
    print("Testing EmailThread.markdown property...")
    
    # Get a recent message to test with
    print("\n1. Getting recent inbox messages...")
    messages = await get_recent_inbox_messages(count=3)
    
    if not messages:
        print("❌ No messages found in inbox")
        return
    
    print(f"Found {len(messages)} recent messages")
    
    # Get complete thread for the first message
    print(f"\n2. Getting complete thread for: {messages[0].subject}")
    thread = await get_complete_thread(messages[0])
    
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
    print(markdown_content[:500])
    print("=" * 50)
    
    # Optionally save to file for inspection
    output_file = "thread_markdown_output.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"\n✅ Complete markdown saved to: {output_file}")
    print(f"Thread has {thread.message_count} messages formatted as markdown")

if __name__ == "__main__":
    asyncio.run(main()) 
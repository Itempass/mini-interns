#!/usr/bin/env python3
"""
Test script to verify the fixed threading service works correctly.
"""

import sys
import os
import imaplib
from dotenv import load_dotenv

# Add the src directory to the path so we can import our services
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.threading_service import ThreadingService

# Constants
IMAP_SERVER = "imap.gmail.com"
IMAP_USERNAME = "arthur@itempass.com"
IMAP_PORT = 993

load_dotenv(override=True)

def test_threading_service():
    """Test the fixed threading service"""
    
    # Connect to Gmail
    password = os.getenv('IMAP_PASSWORD')
    if not password:
        raise ValueError("IMAP_PASSWORD environment variable not set")
    
    print(f"Connecting to {IMAP_SERVER}...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(IMAP_USERNAME, password)
    
    # Select INBOX and get a sample UID
    mail.select('"INBOX"', readonly=True)
    typ, data = mail.uid('search', None, 'ALL')
    
    if typ != 'OK' or not data[0]:
        print("No messages found in INBOX")
        return
    
    # Get the last UID as our test case
    all_uids = data[0].split()
    test_uid = "5961"  # Use the UID from our experiment that has a known thread
    
    # Verify the UID exists in the mailbox
    if test_uid.encode() not in all_uids:
        print(f"UID {test_uid} not found in INBOX, using last UID instead")
        test_uid = all_uids[-1].decode()
    
    print(f"\n=== Testing Threading Service with UID: {test_uid} ===")
    
    # Initialize the threading service
    threading_service = ThreadingService(mail)
    
    # Test the threading functionality
    try:
        mailbox, thread_uids = threading_service.get_thread_uids(test_uid, "INBOX")
        print(f"✓ Thread search completed successfully!")
        print(f"  - Found mailbox: {mailbox}")
        print(f"  - Thread UIDs: {thread_uids}")
        print(f"  - Thread size: {len(thread_uids)} messages")
        
        if len(thread_uids) > 1:
            print("✓ Thread contains multiple messages - threading is working!")
        else:
            print("ℹ Thread contains only one message (might be a standalone message)")
            
    except Exception as e:
        print(f"✗ Error testing threading service: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("\nClosing connection...")
        mail.close()
        mail.logout()

if __name__ == "__main__":
    print("Testing Fixed Threading Service...")
    test_threading_service()
    print("Test completed!") 
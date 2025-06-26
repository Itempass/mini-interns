#!/usr/bin/env python3
"""
Minimal Gmail Threading Test

Fetches the last 20 emails from inbox and gets complete threads for each,
measuring performance.
"""

import imaplib
import email
import os
import logging
import re
import base64
import time
from typing import List, Optional, Tuple
from dotenv import load_dotenv

# Constants
IMAP_SERVER = "imap.gmail.com"
IMAP_USERNAME = "arthur@itempass.com"
IMAP_PORT = 993

load_dotenv(override=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class InboxThreadingTest:
    def __init__(self):
        self.mail = None
    
    def connect(self):
        """Connect to Gmail IMAP"""
        password = os.getenv('IMAP_PASSWORD')
        if not password:
            raise ValueError("IMAP_PASSWORD environment variable not set")
        
        logger.info(f"Connecting to {IMAP_SERVER}...")
        self.mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        self.mail.login(IMAP_USERNAME, password)
        logger.info("Connected successfully!")
    
    def create_contextual_id(self, mailbox: str, uid: str) -> str:
        """Creates a contextual ID from a mailbox and a UID."""
        encoded_mailbox = base64.b64encode(mailbox.encode('utf-8')).decode('utf-8')
        return f"{encoded_mailbox}:{uid}"
    
    def _extract_body(self, msg) -> str:
        """Extract the body text from an email message"""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    charset = part.get_content_charset() or 'utf-8'
                    body = part.get_payload(decode=True).decode(charset, errors='ignore')
                    break
        else:
            charset = msg.get_content_charset() or 'utf-8'
            body = msg.get_payload(decode=True)
            if isinstance(body, bytes):
                body = body.decode(charset, errors='ignore')
        return body or ""
    
    def _find_uid_by_message_id(self, message_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Find UID and mailbox for a given Message-ID header."""
        mailboxes_to_search = ["INBOX", "[Gmail]/All Mail", "[Gmail]/Sent Mail"]
        
        for mailbox in mailboxes_to_search:
            try:
                self.mail.select(f'"{mailbox}"', readonly=True)
                typ, data = self.mail.uid('search', None, f'(HEADER Message-ID "{message_id}")')
                
                if typ == 'OK' and data and data[0]:
                    uids = data[0].split()
                    if uids:
                        uid = uids[0].decode()
                        return uid, mailbox
            except Exception as e:
                logger.warning(f"Error searching {mailbox}: {e}")
                continue
        
        return None, None
    
    def get_complete_thread_with_folders(self, message_id: str) -> Optional[List[dict]]:
        """
        Get complete thread with folder information for a given Message-ID.
        Returns thread messages with contextual IDs and Gmail labels.
        
        Returns:
            List of message dictionaries:
            [
                {
                    "uid": "contextual_id (base64_mailbox:uid)",
                    "message_id": "unique-message-id", 
                    "from": "sender@example.com",
                    "to": "recipient@example.com",
                    "cc": "cc@example.com",
                    "bcc": "bcc@example.com", 
                    "subject": "Email subject",
                    "date": "email date",
                    "body": "email body text",
                    "gmail_labels": ["\\Inbox", "\\Important"],
                    "references": "references header",
                    "in_reply_to": "in-reply-to message id"
                },
                ...
            ]
        """
        try:
            # Step 1: Find the message and get its thread ID
            uid, mailbox = self._find_uid_by_message_id(message_id)
            if not uid:
                return None
            
            # Step 2: Get X-GM-THRID from the message
            self.mail.select(f'"{mailbox}"', readonly=True)
            typ, data = self.mail.uid('fetch', uid, '(X-GM-THRID)')
            if typ != 'OK' or not data:
                return None
            
            thrid_match = re.search(rb'X-GM-THRID (\d+)', data[0])
            if not thrid_match:
                return None
            
            gmail_thread_id = thrid_match.group(1).decode()
            
            # Step 3: Search for all thread messages in All Mail
            self.mail.select('"[Gmail]/All Mail"', readonly=True)
            typ, data = self.mail.uid('search', None, f'(X-GM-THRID {gmail_thread_id})')
            if typ != 'OK' or not data:
                return None
            
            thread_uids = [uid.decode() for uid in data[0].split()]
            
            # Step 4: Fetch all messages with labels in one call
            uid_list = ','.join(thread_uids)
            typ, data = self.mail.uid('fetch', uid_list, '(RFC822 X-GM-LABELS)')
            if typ != 'OK' or not data:
                return None
            
            # Step 5: Parse messages and labels
            messages = []
            i = 0
            while i < len(data):
                if isinstance(data[i], tuple) and len(data[i]) >= 2:
                    # The tuple contains both the header info and the email body
                    header_info = data[i][0].decode() if isinstance(data[i][0], bytes) else str(data[i][0])
                    msg = email.message_from_bytes(data[i][1])
                    message_id_header = msg.get('Message-ID', '').strip('<>')
                    
                    # Skip draft messages (no Message-ID)
                    if not message_id_header:
                        i += 1
                        continue
                    
                    # Extract UID from header info
                    uid_match = re.search(r'(\d+) \(', header_info)
                    uid = uid_match.group(1) if uid_match else thread_uids[len(messages)]
                    
                    # Create contextual ID (we're fetching from [Gmail]/All Mail)
                    contextual_id = self.create_contextual_id('[Gmail]/All Mail', uid)
                    
                    # Extract Gmail labels from header info
                    labels = []
                    labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
                    if labels_match:
                        labels_str = labels_match.group(1)
                        # Parse quoted labels - they come as "label1" "label2" etc
                        labels = re.findall(r'"([^"]*)"', labels_str)
                        # Clean up escaped backslashes
                        labels = [label.replace('\\\\', '\\') for label in labels]
                    
                    messages.append({
                        'uid': contextual_id,
                        'message_id': message_id_header,
                        'from': msg.get('From', ''),
                        'to': msg.get('To', ''),
                        'cc': msg.get('Cc', ''),
                        'bcc': msg.get('Bcc', ''),
                        'subject': msg.get('Subject', ''),
                        'date': msg.get('Date', ''),
                        'body': self._extract_body(msg),
                        'gmail_labels': labels,
                        'references': msg.get('References', ''),
                        'in_reply_to': msg.get('In-Reply-To', '').strip('<>')
                    })
                i += 1
            
            # Step 6: Sort chronologically
            messages.sort(key=lambda m: m.get('date', ''))
            
            return messages
            
        except Exception as e:
            logger.error(f"Error getting thread: {e}")
            return None
    
    def get_recent_inbox_emails(self, count: int = 20) -> List[str]:
        """Get Message-IDs of recent emails from INBOX"""
        try:
            self.mail.select('"INBOX"', readonly=True)
            typ, data = self.mail.uid('search', None, 'ALL')
            
            if typ != 'OK' or not data:
                return []
            
            # Get recent UIDs
            all_uids = data[0].split()
            recent_uids = all_uids[-count:] if len(all_uids) >= count else all_uids
            
            # Fetch Message-IDs for these UIDs
            message_ids = []
            for uid in recent_uids:
                typ, data = self.mail.uid('fetch', uid, '(BODY[HEADER.FIELDS (MESSAGE-ID)])')
                if typ == 'OK' and data and data[0]:
                    for response_part in data:
                        if isinstance(response_part, tuple):
                            headers = response_part[1].decode()
                            message_id_match = re.search(r'Message-ID:\s*<([^>]+)>', headers, re.IGNORECASE)
                            if message_id_match:
                                message_ids.append(message_id_match.group(1))
                            break
            
            return message_ids
            
        except Exception as e:
            logger.error(f"Error getting inbox emails: {e}")
            return []
    
    def run_threading_test(self):
        """Run the complete threading test"""
        try:
            self.connect()
            
            # Step 1: Get recent inbox emails
            logger.info("=== FETCHING RECENT INBOX EMAILS ===")
            start_time = time.time()
            
            message_ids = self.get_recent_inbox_emails(20)
            
            inbox_time = time.time() - start_time
            logger.info(f"✓ Found {len(message_ids)} emails in inbox ({inbox_time:.2f}s)")
            
            if not message_ids:
                logger.warning("No emails found in inbox")
                return
            
            # Step 2: Get threads for each email
            logger.info("\n=== FETCHING THREADS FOR EACH EMAIL ===")
            threading_start = time.time()
            
            total_messages = 0
            successful_threads = 0
            
            for i, message_id in enumerate(message_ids, 1):
                logger.info(f"Processing email {i}/{len(message_ids)}: {message_id[:50]}...")
                
                thread_start = time.time()
                thread = self.get_complete_thread_with_folders(message_id)
                thread_time = time.time() - thread_start
                
                if thread:
                    successful_threads += 1
                    total_messages += len(thread)
                    logger.info(f"  ✓ Got thread with {len(thread)} messages ({thread_time:.2f}s)")
                else:
                    logger.warning(f"  ✗ Failed to get thread ({thread_time:.2f}s)")
            
            threading_time = time.time() - threading_start
            total_time = time.time() - start_time
            
            # Results
            logger.info("\n=== THREADING TEST RESULTS ===")
            logger.info(f"Total emails processed: {len(message_ids)}")
            logger.info(f"Successful threads: {successful_threads}/{len(message_ids)}")
            logger.info(f"Total messages in all threads: {total_messages}")
            logger.info(f"Average messages per thread: {total_messages/successful_threads:.1f}")
            logger.info(f"Inbox fetch time: {inbox_time:.2f}s")
            logger.info(f"Threading time: {threading_time:.2f}s")
            logger.info(f"Total time: {total_time:.2f}s")
            logger.info(f"Average time per thread: {threading_time/len(message_ids):.2f}s")
            
        except Exception as e:
            logger.error(f"Test failed: {e}")
        finally:
            if self.mail:
                self.mail.close()
                self.mail.logout()

if __name__ == "__main__":
    logger.info("Starting Inbox Threading Test...")
    
    test = InboxThreadingTest()
    test.run_threading_test()
    
    logger.info("Test completed!") 
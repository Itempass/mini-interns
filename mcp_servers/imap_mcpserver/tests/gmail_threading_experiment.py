#!/usr/bin/env python3
"""
Gmail Threading Experiment Script

This script connects to Gmail IMAP and experiments with different threading approaches
to understand how Gmail's threading works.
"""

import imaplib
import email
import os
import logging
import re
import base64
from typing import List, Optional, Tuple
from dotenv import load_dotenv

# Constants - Update these for your Gmail account
IMAP_SERVER = "imap.gmail.com"
IMAP_USERNAME = "arthur@itempass.com"  # Update this
IMAP_PORT = 993

load_dotenv(override=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GmailThreadingExperiment:
    def __init__(self):
        self.mail = None
        self.capabilities = []
    
    def connect(self):
        """Connect to Gmail IMAP"""
        password = os.getenv('IMAP_PASSWORD')
        if not password:
            raise ValueError("IMAP_PASSWORD environment variable not set")
        
        logger.info(f"Connecting to {IMAP_SERVER}...")
        self.mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        
        logger.info(f"Logging in as {IMAP_USERNAME}...")
        self.mail.login(IMAP_USERNAME, password)
        
        # Get capabilities
        typ, data = self.mail.capability()
        if typ == 'OK':
            self.capabilities = [cap.upper() for cap in data[0].decode().split()]
            logger.info(f"Server capabilities: {', '.join(sorted(self.capabilities))}")
        
        logger.info("Connected successfully!")
    
    def list_mailboxes(self):
        """List available mailboxes"""
        logger.info("\n=== MAILBOXES ===")
        typ, mailboxes = self.mail.list()
        if typ == 'OK':
            for mailbox in mailboxes:
                logger.info(f"Mailbox: {mailbox.decode()}")
    
    def select_mailbox_and_get_sample_uids(self, mailbox="INBOX", limit=5):
        """Select a mailbox and get some sample UIDs"""
        logger.info(f"\n=== SELECTING MAILBOX: {mailbox} ===")
        
        try:
            self.mail.select(f'"{mailbox}"', readonly=True)
            logger.info(f"Selected mailbox: {mailbox}")
            
            # Get some recent UIDs
            typ, data = self.mail.uid('search', None, 'ALL')
            if typ == 'OK' and data[0]:
                all_uids = data[0].split()
                sample_uids = all_uids[-limit:]  # Get last N UIDs
                logger.info(f"Sample UIDs: {[uid.decode() for uid in sample_uids]}")
                return [uid.decode() for uid in sample_uids]
            else:
                logger.warning(f"No messages found in {mailbox}")
                return []
        except Exception as e:
            logger.error(f"Error selecting mailbox {mailbox}: {e}")
            return []
    
    def test_thread_capabilities(self):
        """Test what threading capabilities Gmail supports"""
        logger.info("\n=== TESTING THREAD CAPABILITIES ===")
        
        thread_caps = [cap for cap in self.capabilities if 'THREAD' in cap]
        logger.info(f"Thread-related capabilities: {thread_caps}")
        
        gmail_caps = [cap for cap in self.capabilities if 'GM' in cap]
        logger.info(f"Gmail-specific capabilities: {gmail_caps}")
        
        return 'THREAD=REFERENCES' in self.capabilities, 'X-GM-EXT-1' in self.capabilities
    
    def test_imap_thread_command(self, test_uid: str):
        """Test the standard IMAP THREAD command"""
        logger.info(f"\n=== TESTING IMAP THREAD COMMAND FOR UID {test_uid} ===")
        
        if 'THREAD=REFERENCES' not in self.capabilities:
            logger.warning("Server doesn't support THREAD=REFERENCES")
            return None
        
        try:
            # Try the THREAD command
            typ, data = self.mail.uid('thread', 'REFERENCES', 'UTF-8', 'ALL')
            if typ == 'OK' and data and data[0]:
                thread_data = data[0].decode()
                logger.info(f"Raw THREAD response: {thread_data}")
                
                # Parse the response to find our UID
                # Response format: (uid1 uid2) (uid3 uid4 uid5) ...
                threads = self._parse_thread_response(thread_data)
                logger.info(f"Parsed threads: {threads}")
                
                # Find which thread contains our UID
                for thread in threads:
                    if test_uid in thread:
                        logger.info(f"Found UID {test_uid} in thread: {thread}")
                        return thread
                
                logger.warning(f"UID {test_uid} not found in any thread")
                return None
            else:
                logger.warning("THREAD command failed or returned no data")
                return None
                
        except Exception as e:
            logger.error(f"Error with THREAD command: {e}")
            return None
    
    def test_gmail_thrid(self, test_uid: str):
        """Test Gmail's X-GM-THRID approach"""
        logger.info(f"\n=== TESTING GMAIL X-GM-THRID FOR UID {test_uid} ===")
        
        if 'X-GM-EXT-1' not in self.capabilities:
            logger.warning("Server doesn't support Gmail extensions")
            return None
        
        try:
            # Fetch the X-GM-THRID for our test message
            typ, data = self.mail.uid('fetch', test_uid, '(X-GM-THRID)')
            if typ != 'OK' or not data or not data[0]:
                logger.warning(f"Could not fetch X-GM-THRID for UID {test_uid}")
                return None
            
            logger.info(f"Raw X-GM-THRID response: {data[0]}")
            
            # Parse the thread ID
            thrid_match = re.search(rb'X-GM-THRID (\d+)', data[0])
            if not thrid_match:
                logger.warning("Could not parse X-GM-THRID from response")
                return None
            
            gmail_thread_id = thrid_match.group(1).decode()
            logger.info(f"Found X-GM-THRID: {gmail_thread_id}")
            
            # Now try different ways to search for this thread ID
            return self._test_gmail_thread_searches(gmail_thread_id)
            
        except Exception as e:
            logger.error(f"Error with X-GM-THRID: {e}")
            return None
    
    def _test_gmail_thread_searches(self, thread_id: str):
        """Test different ways to search for Gmail thread"""
        logger.info(f"\n=== TESTING DIFFERENT GMAIL SEARCH METHODS FOR THRID {thread_id} ===")
        
        search_methods = [
            # Method 1: X-GM-RAW with thrid
            ('X-GM-RAW', f'thrid:{thread_id}'),
            
            # Method 2: X-GM-RAW with thrid excluding drafts
            ('X-GM-RAW', f'thrid:{thread_id} -in:drafts'),
            
            # Method 3: Direct X-GM-THRID search (if supported)
            ('X-GM-THRID', thread_id),
        ]
        
        results = {}
        current_mailbox = None
        
        # Try searches in different mailboxes
        mailboxes_to_try = ['INBOX', '[Gmail]/All Mail', '[Gmail]/Sent Mail']
        
        for mailbox in mailboxes_to_try:
            logger.info(f"\n--- Testing in mailbox: {mailbox} ---")
            try:
                self.mail.select(f'"{mailbox}"', readonly=True)
                current_mailbox = mailbox
                
                for method_name, search_query in search_methods:
                    logger.info(f"Trying {method_name} search: {search_query}")
                    try:
                        if method_name == 'X-GM-RAW':
                            typ, data = self.mail.uid('search', None, f'({method_name} "{search_query}")')
                        else:
                            typ, data = self.mail.uid('search', None, f'({method_name} {search_query})')
                        
                        if typ == 'OK' and data and data[0]:
                            uids = [uid.decode() for uid in data[0].split()]
                            logger.info(f"✓ Found {len(uids)} UIDs: {uids}")
                            results[f"{mailbox}_{method_name}"] = uids
                        else:
                            logger.info("✗ No results")
                            results[f"{mailbox}_{method_name}"] = []
                            
                    except Exception as e:
                        logger.error(f"✗ Error with {method_name}: {e}")
                        results[f"{mailbox}_{method_name}"] = None
                        
            except Exception as e:
                logger.error(f"Could not select mailbox {mailbox}: {e}")
        
        return results
    
    def _parse_thread_response(self, thread_data: str) -> List[List[str]]:
        """Parse IMAP THREAD response format"""
        threads = []
        
        # Remove outer parentheses and split by thread groups
        cleaned = thread_data.strip()
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = cleaned[1:-1]
        
        # Split by ') (' to get individual threads
        thread_groups = cleaned.split(') (')
        
        for group in thread_groups:
            group = group.strip('() ')
            if group:
                uids = group.split()
                threads.append(uids)
        
        return threads
    
    def get_message_headers(self, uid: str):
        """Get message headers for analysis"""
        logger.info(f"\n=== MESSAGE HEADERS FOR UID {uid} ===")
        
        try:
            typ, data = self.mail.uid('fetch', uid, '(BODY[HEADER.FIELDS (MESSAGE-ID REFERENCES IN-REPLY-TO SUBJECT FROM DATE)])')
            if typ == 'OK' and data and data[0]:
                for response_part in data:
                    if isinstance(response_part, tuple):
                        headers = response_part[1].decode()
                        logger.info(f"Headers:\n{headers}")
                        return headers
        except Exception as e:
            logger.error(f"Error fetching headers for UID {uid}: {e}")
        
        return None
    
    def run_experiment(self):
        """Run the full threading experiment"""
        try:
            self.connect()
            self.list_mailboxes()
            
            # Test threading capabilities
            has_thread, has_gmail = self.test_thread_capabilities()
            
            # Get some sample UIDs from INBOX
            sample_uids = self.select_mailbox_and_get_sample_uids("INBOX", 3)
            
            if not sample_uids:
                logger.warning("No sample UIDs found, trying [Gmail]/Sent Mail")
                sample_uids = self.select_mailbox_and_get_sample_uids("[Gmail]/Sent Mail", 3)
            
            if not sample_uids:
                logger.error("No messages found to test with")
                return
            
            # Test with the first UID
            test_uid = sample_uids[0]
            logger.info(f"\n=== TESTING WITH UID: {test_uid} ===")
            
            # Get message headers for context
            self.get_message_headers(test_uid)
            
            # Test IMAP THREAD command
            if has_thread:
                thread_result = self.test_imap_thread_command(test_uid)
                logger.info(f"IMAP THREAD result: {thread_result}")
            
            # Test Gmail THRID
            if has_gmail:
                gmail_result = self.test_gmail_thrid(test_uid)
                logger.info(f"Gmail THRID results: {gmail_result}")
                
                # Now test efficient thread fetching
                self.test_complete_thread_fetching(test_uid)
            
        except Exception as e:
            logger.error(f"Experiment failed: {e}")
        finally:
            if self.mail:
                logger.info("Closing connection...")
                self.mail.close()
                self.mail.logout()

    def test_complete_thread_fetching(self, message_uid: str):
        """Test different approaches for fetching complete thread data efficiently"""
        logger.info(f"\n=== TESTING COMPLETE THREAD FETCHING FOR UID {message_uid} ===")
        
        # First get the thread UIDs using our working method
        thread_uids = self._get_thread_uids_efficiently(message_uid)
        if not thread_uids:
            logger.warning("Could not get thread UIDs, skipping complete fetch test")
            return
        
        logger.info(f"Thread has {len(thread_uids)} messages: {thread_uids}")
        
        # Test different fetching strategies
        self._test_batch_fetch_strategies(thread_uids)
        
        # Test the complete pipeline
        complete_thread = self._fetch_complete_thread_data(thread_uids)
        if complete_thread:
            logger.info(f"✓ Complete thread fetched successfully!")
            logger.info(f"Sample message structure:")
            if len(complete_thread) > 0:
                sample = complete_thread[0]
                logger.info(f"  - From: {sample.get('from', 'N/A')}")
                logger.info(f"  - Subject: {sample.get('subject', 'N/A')}")
                logger.info(f"  - Message-ID: {sample.get('message_id', 'N/A')}")
                logger.info(f"  - Body length: {len(sample.get('body', ''))}")
    
    def _get_thread_uids_efficiently(self, message_uid: str) -> Optional[List[str]]:
        """Get thread UIDs using our proven Gmail method"""
        try:
            # Make sure we're in the right mailbox for the initial UID
            self.mail.select('"INBOX"', readonly=True)
            
            # Fetch X-GM-THRID
            typ, data = self.mail.uid('fetch', message_uid, '(X-GM-THRID)')
            if typ != 'OK' or not data or not data[0]:
                return None
            
            thrid_match = re.search(rb'X-GM-THRID (\d+)', data[0])
            if not thrid_match:
                return None
            
            gmail_thread_id = thrid_match.group(1).decode()
            
            # Switch to All Mail for complete results
            self.mail.select('"[Gmail]/All Mail"', readonly=True)
            
            # Search for all UIDs in thread
            typ, data = self.mail.uid('search', None, f'(X-GM-THRID {gmail_thread_id})')
            if typ != 'OK' or not data or not data[0]:
                return None
            
            uids = [uid.decode() for uid in data[0].split()]
            return uids
            
        except Exception as e:
            logger.error(f"Error getting thread UIDs: {e}")
            return None
    
    def _test_batch_fetch_strategies(self, uids: List[str]):
        """Test different strategies for batch fetching message data"""
        logger.info(f"\n--- Testing Batch Fetch Strategies ---")
        
        if len(uids) > 5:  # Only test with first 5 for speed
            test_uids = uids[:5]
            logger.info(f"Testing with first 5 UIDs: {test_uids}")
        else:
            test_uids = uids
        
        strategies = [
            ("Individual fetches", self._fetch_individual),
            ("Batch UID range", self._fetch_batch_range),
            ("Batch UID list", self._fetch_batch_list),
        ]
        
        for strategy_name, strategy_func in strategies:
            logger.info(f"\nTesting strategy: {strategy_name}")
            try:
                import time
                start_time = time.time()
                
                result = strategy_func(test_uids)
                
                end_time = time.time()
                duration = end_time - start_time
                
                if result:
                    logger.info(f"✓ {strategy_name}: {len(result)} messages in {duration:.2f}s")
                else:
                    logger.info(f"✗ {strategy_name}: Failed")
                    
            except Exception as e:
                logger.error(f"✗ {strategy_name}: Error - {e}")
    
    def _fetch_individual(self, uids: List[str]) -> Optional[List[dict]]:
        """Strategy 1: Fetch messages individually (slowest but most reliable)"""
        messages = []
        for uid in uids:
            typ, data = self.mail.uid('fetch', uid, '(RFC822)')
            if typ == 'OK' and data and data[0]:
                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        messages.append(self._parse_message(msg, uid))
        return messages if messages else None
    
    def _fetch_batch_range(self, uids: List[str]) -> Optional[List[dict]]:
        """Strategy 2: Fetch using UID range (fast if UIDs are sequential)"""
        if not uids:
            return None
        
        # Sort UIDs to create ranges
        sorted_uids = sorted([int(uid) for uid in uids])
        uid_range = f"{sorted_uids[0]}:{sorted_uids[-1]}"
        
        typ, data = self.mail.uid('fetch', uid_range, '(RFC822)')
        if typ != 'OK' or not data:
            return None
        
        messages = []
        i = 0
        while i < len(data):
            if isinstance(data[i], tuple):
                msg = email.message_from_bytes(data[i][1])
                # Extract UID from the response
                uid_match = re.search(rb'(\d+) \(', data[i-1] if i > 0 else b'')
                uid = uid_match.group(1).decode() if uid_match else str(sorted_uids[len(messages)])
                messages.append(self._parse_message(msg, uid))
            i += 1
        
        return messages if messages else None
    
    def _fetch_batch_list(self, uids: List[str]) -> Optional[List[dict]]:
        """Strategy 3: Fetch using comma-separated UID list"""
        if not uids:
            return None
        
        uid_list = ','.join(uids)
        typ, data = self.mail.uid('fetch', uid_list, '(RFC822)')
        if typ != 'OK' or not data:
            return None
        
        messages = []
        i = 0
        while i < len(data):
            if isinstance(data[i], tuple):
                msg = email.message_from_bytes(data[i][1])
                # Extract UID from the response
                uid_match = re.search(rb'(\d+) \(', data[i-1] if i > 0 else b'')
                uid = uid_match.group(1).decode() if uid_match else uids[len(messages)]
                messages.append(self._parse_message(msg, uid))
            i += 1
        
        return messages if messages else None
    
    def _fetch_complete_thread_data(self, uids: List[str]) -> Optional[List[dict]]:
        """Fetch complete thread data using the most efficient method"""
        logger.info(f"\n--- Fetching Complete Thread Data ---")
        
        try:
            # Use batch list strategy (usually most reliable)
            return self._fetch_batch_list(uids)
        except Exception as e:
            logger.error(f"Batch fetch failed, falling back to individual: {e}")
            return self._fetch_individual(uids)
    
    def _parse_message(self, msg, uid: str) -> dict:
        """Parse an email message into a structured format"""
        
        # Extract headers
        headers = {
            'message_id': msg.get('Message-ID', '').strip('<>'),
            'from': msg.get('From', ''),
            'to': msg.get('To', ''),
            'cc': msg.get('CC', ''),
            'subject': msg.get('Subject', ''),
            'date': msg.get('Date', ''),
            'references': msg.get('References', ''),
            'in_reply_to': msg.get('In-Reply-To', '').strip('<>'),
        }
        
        # Extract body
        body = self._extract_body(msg)
        
        return {
            'uid': uid,
            'headers': headers,
            'from': headers['from'],
            'to': headers['to'],
            'subject': headers['subject'],
            'message_id': headers['message_id'],
            'date': headers['date'],
            'body': body,
            'references': headers['references'],
            'in_reply_to': headers['in_reply_to'],
        }
    
    def _extract_body(self, msg) -> str:
        """Extract the body text from an email message"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    charset = part.get_content_charset() or 'utf-8'
                    body = part.get_payload(decode=True).decode(charset, errors='ignore')
                    break
                elif part.get_content_type() == "text/html" and not body:
                    # Fallback to HTML if no plain text
                    charset = part.get_content_charset() or 'utf-8'
                    body = part.get_payload(decode=True).decode(charset, errors='ignore')
        else:
            charset = msg.get_content_charset() or 'utf-8'
            body = msg.get_payload(decode=True)
            if isinstance(body, bytes):
                body = body.decode(charset, errors='ignore')
        
        return body or ""

    # Contextual ID utilities (from your contextual_id.py)
    def create_contextual_id(self, mailbox: str, uid: str) -> str:
        """Creates a contextual ID from a mailbox and a UID."""
        encoded_mailbox = base64.b64encode(mailbox.encode('utf-8')).decode('utf-8')
        return f"{encoded_mailbox}:{uid}"

    def parse_contextual_id(self, contextual_id: str) -> Tuple[str, str]:
        """
        Parses a contextual ID into a mailbox and a UID.
        If parsing fails, it assumes the ID is a simple UID from INBOX.
        """
        try:
            encoded_mailbox, uid = contextual_id.split(':', 1)
            decoded_mailbox = base64.b64decode(encoded_mailbox.encode('utf-8')).decode('utf-8')
            return decoded_mailbox, uid
        except (ValueError, TypeError, base64.binascii.Error):
            return 'INBOX', contextual_id

    def is_valid_contextual_id(self, contextual_id: str) -> bool:
        """Validates if the given ID is a valid contextual ID."""
        if not isinstance(contextual_id, str):
            return False
        parts = contextual_id.split(':', 1)
        if len(parts) != 2:
            return False
        
        encoded_mailbox, uid = parts
        if not uid.isdigit():
            return False

        try:
            base64.b64decode(encoded_mailbox.encode('utf-8'), validate=True)
        except (base64.binascii.Error, ValueError):
            return False

        return True

    def get_complete_thread(self, message_id: str) -> Optional[List[dict]]:
        """
        Enhanced production-ready function: Get complete thread data for a given message identifier.
        
        Args:
            message_id: Can be:
                - Contextual ID: "base64_mailbox:uid" (e.g., "SU5CT1g=:5961")
                - Plain UID: "5961" (assumes INBOX)
                - Message-ID: "<unique-message-id@domain.com>" (header-based lookup)
            
        Returns:
            List of message dictionaries with structure:
            [
                {
                    "uid": "12345",
                    "contextual_id": "base64_mailbox:uid",
                    "headers": {...},
                    "from": "sender@example.com",
                    "to": "recipient@example.com", 
                    "subject": "Email subject",
                    "message_id": "unique-message-id",
                    "date": "email date",
                    "body": "email body text",
                    "references": "references header",
                    "in_reply_to": "in-reply-to message id"
                },
                ...
            ]
        """
        logger.info(f"Getting complete thread for message ID: {message_id}")
        
        try:
            # Step 1: Determine ID type and get initial UID/mailbox
            initial_uid, initial_mailbox = self._resolve_message_identifier(message_id)
            if not initial_uid:
                logger.warning(f"Could not resolve message identifier: {message_id}")
                return None
                
            logger.info(f"Resolved to UID {initial_uid} in mailbox '{initial_mailbox}'")
            
            # Step 2: Get thread UIDs efficiently
            thread_uids = self._get_thread_uids_from_mailbox(initial_uid, initial_mailbox)
            if not thread_uids:
                logger.warning(f"Could not find thread for UID {initial_uid}")
                return None
                
            logger.info(f"Found thread with {len(thread_uids)} messages")
            
            # Step 3: Fetch all messages using batch UID list
            complete_thread = self._fetch_batch_list(thread_uids)
            if not complete_thread:
                logger.warning(f"Failed to fetch thread messages")
                return None
                
            # Step 4: Filter out draft messages (those without Message-IDs)
            complete_thread = [msg for msg in complete_thread if msg.get('message_id', '').strip()]
            logger.info(f"After filtering drafts: {len(complete_thread)} messages remain")
            
            # Step 5: Enhance messages with contextual IDs
            for msg in complete_thread:
                msg['contextual_id'] = self.create_contextual_id('[Gmail]/All Mail', msg['uid'])
                
            # Step 6: Sort messages chronologically by date
            complete_thread.sort(key=lambda msg: msg.get('date', ''))
            
            logger.info(f"✓ Successfully retrieved complete thread with {len(complete_thread)} messages")
            return complete_thread
            
        except Exception as e:
            logger.error(f"Error getting complete thread for ID {message_id}: {e}")
            return None

    def _resolve_message_identifier(self, message_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve different types of message identifiers to UID and mailbox.
        
        Returns:
            Tuple of (uid, mailbox) or (None, None) if resolution fails
        """
        
        # Type 1: Contextual ID (base64_mailbox:uid)
        if self.is_valid_contextual_id(message_id):
            logger.info(f"Detected contextual ID: {message_id}")
            mailbox, uid = self.parse_contextual_id(message_id)
            return uid, mailbox
        
        # Type 2: Message-ID header (starts with < and ends with >)
        elif message_id.startswith('<') and message_id.endswith('>'):
            logger.info(f"Detected Message-ID header: {message_id}")
            return self._find_uid_by_message_id(message_id)
        
        # Type 3: Plain UID (assume INBOX)
        elif message_id.isdigit():
            logger.info(f"Detected plain UID: {message_id}, assuming INBOX")
            return message_id, "INBOX"
        
        # Type 4: Invalid/unknown format
        else:
            logger.warning(f"Unrecognized message identifier format: {message_id}")
            return None, None

    def _find_uid_by_message_id(self, message_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Find UID and mailbox for a given Message-ID header."""
        
        # Search in common mailboxes
        mailboxes_to_search = ["INBOX", "[Gmail]/All Mail", "[Gmail]/Sent Mail"]
        
        for mailbox in mailboxes_to_search:
            try:
                logger.info(f"Searching for Message-ID in {mailbox}")
                self.mail.select(f'"{mailbox}"', readonly=True)
                
                # Search for the Message-ID
                typ, data = self.mail.uid('search', None, f'(HEADER Message-ID "{message_id}")')
                
                if typ == 'OK' and data and data[0]:
                    uids = data[0].split()
                    if uids:
                        uid = uids[0].decode()
                        logger.info(f"✓ Found Message-ID in {mailbox} with UID {uid}")
                        return uid, mailbox
                        
            except Exception as e:
                logger.warning(f"Error searching {mailbox} for Message-ID: {e}")
                continue
        
        logger.warning(f"Message-ID {message_id} not found in any mailbox")
        return None, None

    def _get_thread_uids_from_mailbox(self, message_uid: str, source_mailbox: str) -> Optional[List[str]]:
        """Get thread UIDs starting from a specific mailbox."""
        try:
            # Select the source mailbox first
            self.mail.select(f'"{source_mailbox}"', readonly=True)
            
            # Fetch X-GM-THRID
            typ, data = self.mail.uid('fetch', message_uid, '(X-GM-THRID)')
            if typ != 'OK' or not data or not data[0]:
                return None
            
            thrid_match = re.search(rb'X-GM-THRID (\d+)', data[0])
            if not thrid_match:
                return None
            
            gmail_thread_id = thrid_match.group(1).decode()
            logger.info(f"Found X-GM-THRID: {gmail_thread_id}")
            
            # Switch to All Mail for complete results
            logger.info(f"Switching to '[Gmail]/All Mail' for complete thread")
            self.mail.select('"[Gmail]/All Mail"', readonly=True)
            
            # Search for all UIDs in thread
            typ, data = self.mail.uid('search', None, f'(X-GM-THRID {gmail_thread_id})')
            if typ != 'OK' or not data or not data[0]:
                return None
            
            uids = [uid.decode() for uid in data[0].split()]
            return uids
            
        except Exception as e:
            logger.error(f"Error getting thread UIDs from {source_mailbox}: {e}")
            return None



    def get_complete_thread_with_folders(self, message_id: str) -> Optional[List[dict]]:
        """
        Get complete thread with folder information for a given Message-ID.
        Returns thread messages with their Gmail labels (folders) included.
        
        Returns:
            List of message dictionaries with contextual IDs:
            [
                {
                    "uid": "contextual_id (base64_mailbox:uid)",
                    "message_id": "unique-message-id",
                    "from": "sender@example.com",
                    "to": "recipient@example.com", 
                    "subject": "Email subject",
                    "date": "email date",
                    "body": "email body text",
                    "gmail_labels": ["\\Inbox", "\\Important"],  # folder information!
                    "references": "references header",
                    "in_reply_to": "in-reply-to message id"
                },
                ...
            ]
        """
        logger.info(f"Getting complete thread with folders for: {message_id}")
        
        try:
            # Step 1: Find the message and get its thread ID
            uid, mailbox = self._find_uid_by_message_id(message_id)
            if not uid:
                logger.warning(f"Message-ID {message_id} not found")
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
            logger.info(f"Fetching {len(thread_uids)} messages with X-GM-LABELS...")
            typ, data = self.mail.uid('fetch', uid_list, '(RFC822 X-GM-LABELS)')
            if typ != 'OK' or not data:
                logger.warning(f"Fetch failed: {typ}")
                return None
            
            logger.info(f"Fetch returned {len(data)} response parts")
            
            # Debug: Print first few response parts to see the structure
            for i, part in enumerate(data[:4]):  # Look at first few parts
                logger.info(f"Response part {i}: {type(part)} - {str(part)[:200]}...")
            
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
                        logger.info(f"Found labels string: '{labels_str}'")
                        # Parse quoted labels - they come as "label1" "label2" etc
                        labels = re.findall(r'"([^"]*)"', labels_str)
                        # Clean up escaped backslashes
                        labels = [label.replace('\\\\', '\\') for label in labels]
                        logger.info(f"Parsed labels: {labels}")
                    else:
                        logger.debug(f"No X-GM-LABELS found in header: {header_info}")
                    
                    messages.append({
                        'uid': contextual_id,  # Now using contextual ID instead of plain UID
                        'message_id': message_id_header,
                        'from': msg.get('From', ''),
                        'to': msg.get('To', ''),
                        'subject': msg.get('Subject', ''),
                        'date': msg.get('Date', ''),
                        'body': self._extract_body(msg),
                        'gmail_labels': labels,  # This is the folder information!
                        'references': msg.get('References', ''),
                        'in_reply_to': msg.get('In-Reply-To', '').strip('<>')
                    })
                i += 1
            
            # Step 6: Sort chronologically
            messages.sort(key=lambda m: m.get('date', ''))
            
            logger.info(f"✓ Retrieved {len(messages)} messages with folder information")
            return messages
            
        except Exception as e:
            logger.error(f"Error getting thread with folders: {e}")
            return None

if __name__ == "__main__":
    logger.info("Starting Gmail Threading Experiment...")
    
    experiment = GmailThreadingExperiment()
    
    # Test Message-ID based thread fetching performance
    try:
        experiment.connect()
        
        # Test with a known Message-ID from our previous results
        test_message_id = "<CAPajfhLATt77P0LNsa_b0VFkkUAYR8DB=kSxPsfWRWdh+os2gQ@mail.gmail.com>"
        
        logger.info(f"=== TESTING MESSAGE-ID BASED THREAD FETCHING ===")
        logger.info(f"Message-ID: {test_message_id}")
        
        import time
        start_time = time.time()
        
        result = experiment.get_complete_thread_with_folders(test_message_id)
        
        end_time = time.time()
        duration = end_time - start_time
        
        if result:
            logger.info(f"✓ SUCCESS: Retrieved thread with {len(result)} messages in {duration:.2f}s")
            logger.info(f"\n=== ALL {len(result)} MESSAGES IN THREAD ===")
            for i, msg in enumerate(result, 1):
                logger.info(f"Message {i}:")
                logger.info(f"  UID: {msg.get('uid')}")
                logger.info(f"  From: {msg.get('from', 'N/A')}")
                logger.info(f"  Subject: {msg.get('subject', 'N/A')}")
                logger.info(f"  Date: {msg.get('date', 'N/A')}")
                logger.info(f"  Message-ID: {msg.get('message_id', 'N/A')}")
                logger.info(f"  Gmail Labels: {msg.get('gmail_labels', [])}")
                logger.info(f"  In-Reply-To: {msg.get('in_reply_to', 'N/A')}")
                logger.info(f" Body: {msg.get('body', 'N/A')}")
                logger.info("")
        else:
            logger.error(f"✗ FAILED: Could not retrieve thread in {duration:.2f}s")
            
    except Exception as e:
        logger.error(f"Error testing Message-ID based fetching: {e}")
    finally:
        if hasattr(experiment, 'mail') and experiment.mail:
            experiment.mail.close()
            experiment.mail.logout()
    
    logger.info("Experiment completed!") 
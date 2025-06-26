import asyncio
import logging
import sys
import os
import time
import imaplib
import email
import re
from typing import List, Set, Dict, Optional, Tuple
from collections import defaultdict

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from imap_client.models import EmailMessage, EmailThread

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# IMAP connection details
IMAP_SERVER = "imap.gmail.com"
IMAP_USERNAME = os.getenv("IMAP_USERNAME", "arthur@itempass.com")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")
IMAP_PORT = 993

def _create_contextual_id(mailbox: str, uid: str) -> str:
    """Creates a contextual ID from a mailbox and a UID."""
    import base64
    encoded_mailbox = base64.b64encode(mailbox.encode('utf-8')).decode('utf-8')
    return f"{encoded_mailbox}:{uid}"

def _extract_body_formats(msg) -> Dict[str, str]:
    """Simplified body extraction for testing"""
    html_body = ""
    text_body = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            charset = part.get_content_charset() or 'utf-8'
            
            if content_type == "text/plain" and not text_body:
                text_body = part.get_payload(decode=True).decode(charset, errors='ignore')
            elif content_type == "text/html" and not html_body:
                html_body = part.get_payload(decode=True).decode(charset, errors='ignore')
    else:
        charset = msg.get_content_charset() or 'utf-8'
        content = msg.get_payload(decode=True)
        if isinstance(content, bytes):
            content = content.decode(charset, errors='ignore')
        
        if msg.get_content_type() == "text/html":
            html_body = content
        else:
            text_body = content
    
    # Simple body processing
    body = html_body if html_body else text_body
    
    return {
        'raw': body or "",
        'markdown': body or "",
        'cleaned': body or ""
    }

async def fetch_recent_threads_optimized(max_emails_to_scan: int = 50) -> tuple[List[EmailThread], Dict[str, float]]:
    """
    Optimized bulk thread fetching using a single IMAP connection and batch operations.
    
    Strategy:
    1. Single IMAP connection for all operations
    2. Batch fetch recent sent messages
    3. Bulk extract thread IDs using X-GM-THRID
    4. Group thread fetching by mailbox
    5. Batch fetch messages within each mailbox
    """
    start_time = time.time()
    logger.info(f"Starting OPTIMIZED bulk thread fetch, scanning {max_emails_to_scan} recent sent emails")
    
    def _optimized_fetch_sync() -> tuple[List[EmailThread], Dict[str, float]]:
        try:
            # Single connection for everything
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mail.login(IMAP_USERNAME, IMAP_PASSWORD)
            
            try:
                timing = {}
                
                # Step 1: Batch fetch recent sent messages
                fetch_sent_start = time.time()
                mail.select('"[Gmail]/Sent Mail"', readonly=True)
                typ, data = mail.uid('search', None, 'ALL')
                if typ != 'OK' or not data or not data[0]:
                    return [], {"total_time": time.time() - start_time, "error": "No sent messages found"}
                
                email_uids = data[0].split()
                recent_uids = email_uids[-max_emails_to_scan:]
                
                timing['fetch_sent_time'] = time.time() - fetch_sent_start
                logger.info(f"Found {len(recent_uids)} recent sent messages in {timing['fetch_sent_time']:.2f}s")
                
                # Step 2: Get thread IDs for each message (same approach as client.py)
                thread_discovery_start = time.time()
                thread_id_to_messages = defaultdict(list)
                
                logger.info(f"Getting thread IDs for {len(recent_uids)} messages...")
                
                for uid_bytes in recent_uids:
                    uid = uid_bytes.decode()
                    try:
                        # Fetch X-GM-THRID for this specific UID (exactly like client.py)
                        typ, data = mail.uid('fetch', uid, '(X-GM-THRID)')
                        if typ != 'OK' or not data:
                            logger.warning(f"Could not fetch X-GM-THRID for UID {uid}")
                            continue
                        
                        # Extract thread ID from response (same regex as client.py)
                        thrid_match = re.search(rb'X-GM-THRID (\d+)', data[0])
                        if not thrid_match:
                            logger.warning(f"Could not parse X-GM-THRID from response for UID {uid}")
                            continue
                        
                        thread_id = thrid_match.group(1).decode()
                        thread_id_to_messages[thread_id].append(uid)
                        logger.info(f"UID {uid} belongs to thread {thread_id}")
                        
                    except Exception as e:
                        logger.warning(f"Error processing UID {uid}: {e}")
                        continue
                
                timing['thread_discovery_time'] = time.time() - thread_discovery_start
                logger.info(f"Discovered {len(thread_id_to_messages)} unique threads in {timing['thread_discovery_time']:.2f}s")
                
                # Step 3: Bulk fetch complete threads from [Gmail]/All Mail
                bulk_fetch_start = time.time()
                mail.select('"[Gmail]/All Mail"', readonly=True)
                
                threads = []
                for thread_id, sent_uids in thread_id_to_messages.items():
                    # Search for all messages in this thread
                    typ, data = mail.uid('search', None, f'(X-GM-THRID {thread_id})')
                    if typ != 'OK' or not data or not data[0]:
                        continue
                    
                    thread_uids = [uid.decode() for uid in data[0].split()]
                    
                    # Batch fetch all messages in this thread
                    if thread_uids:
                        uid_list = ','.join(thread_uids)
                        typ, data = mail.uid('fetch', uid_list, '(RFC822 X-GM-LABELS)')
                        if typ == 'OK' and data:
                            messages = []
                            
                            j = 0
                            while j < len(data):
                                if isinstance(data[j], tuple) and len(data[j]) >= 2:
                                    header_info = data[j][0].decode() if isinstance(data[j][0], bytes) else str(data[j][0])
                                    msg = email.message_from_bytes(data[j][1])
                                    message_id_header = msg.get('Message-ID', '').strip('<>')
                                    
                                    if message_id_header:
                                        # Extract UID
                                        uid_match = re.search(r'(\d+) \(', header_info)
                                        uid = uid_match.group(1) if uid_match else thread_uids[len(messages)]
                                        
                                        contextual_id = _create_contextual_id('[Gmail]/All Mail', uid)
                                        
                                        # Extract Gmail labels
                                        labels = []
                                        labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
                                        if labels_match:
                                            labels_str = labels_match.group(1)
                                            labels = re.findall(r'"([^"]*)"', labels_str)
                                            labels = [label.replace('\\\\', '\\') for label in labels]
                                        
                                        body_formats = _extract_body_formats(msg)
                                        
                                        messages.append(EmailMessage(
                                            uid=contextual_id,
                                            message_id=message_id_header,
                                            **{'from': msg.get('From', '')},
                                            to=msg.get('To', ''),
                                            cc=msg.get('Cc', ''),
                                            bcc=msg.get('Bcc', ''),
                                            subject=msg.get('Subject', ''),
                                            date=msg.get('Date', ''),
                                            body_raw=body_formats['raw'],
                                            body_markdown=body_formats['markdown'],
                                            body_cleaned=body_formats['cleaned'],
                                            gmail_labels=labels,
                                            references=msg.get('References', ''),
                                            in_reply_to=msg.get('In-Reply-To', '').strip('<>')
                                        ))
                                j += 1
                            
                            if messages:
                                thread = EmailThread.from_messages(messages, thread_id)
                                threads.append(thread)
                
                timing['bulk_fetch_time'] = time.time() - bulk_fetch_start
                timing['total_time'] = time.time() - start_time
                
                logger.info(f"Bulk fetched {len(threads)} complete threads in {timing['bulk_fetch_time']:.2f}s")
                logger.info(f"OPTIMIZED fetch complete: {len(threads)} threads in {timing['total_time']:.2f}s")
                
                return threads, timing
                
            finally:
                try:
                    mail.logout()
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error in optimized fetch: {e}", exc_info=True)
            return [], {"total_time": time.time() - start_time, "error": str(e)}
    
    return await asyncio.get_running_loop().run_in_executor(None, _optimized_fetch_sync)

async def main():
    """Compare optimized vs original approach"""
    logger.info("=== OPTIMIZED Bulk Thread Fetching Test ===")
    
    try:
        for batch_size in [10, 25, 50]:
            logger.info(f"\n--- OPTIMIZED Testing with batch size: {batch_size} ---")
            
            threads, timing_info = await fetch_recent_threads_optimized(max_emails_to_scan=batch_size)
            
            logger.info(f"OPTIMIZED TIMING RESULTS for batch size {batch_size}:")
            for key, value in timing_info.items():
                if isinstance(value, float):
                    logger.info(f"  {key}: {value:.2f}s")
                else:
                    logger.info(f"  {key}: {value}")
            
            if threads:
                total_messages = sum(len(thread.messages) for thread in threads)
                logger.info(f"OPTIMIZED RESULTS:")
                logger.info(f"  threads_found: {len(threads)}")
                logger.info(f"  total_messages: {total_messages}")
                logger.info(f"  avg_messages_per_thread: {total_messages / len(threads):.2f}")
                
                if timing_info.get('total_time', 0) > 0:
                    threads_per_second = len(threads) / timing_info['total_time']
                    messages_per_second = total_messages / timing_info['total_time']
                    logger.info(f"  SPEED: {threads_per_second:.2f} threads/sec, {messages_per_second:.2f} messages/sec")
                    
                    # Compare to original speed (0.54 threads/sec, 1.71 messages/sec)
                    speedup_threads = threads_per_second / 0.54
                    speedup_messages = messages_per_second / 1.71
                    logger.info(f"  SPEEDUP vs Original: {speedup_threads:.1f}x threads, {speedup_messages:.1f}x messages")
    
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 
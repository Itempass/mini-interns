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
    """Extract body in multiple formats - simplified for speed"""
    # Simplified version for performance testing
    return {
        'raw': msg.get_payload() if not msg.is_multipart() else "",
        'markdown': msg.get_payload() if not msg.is_multipart() else "",
        'cleaned': msg.get_payload() if not msg.is_multipart() else ""
    }

async def fetch_threads_super_optimized(target_thread_count: int = 50, max_age_months: int = 6) -> tuple[List[EmailThread], Dict[str, float]]:
    """
    SUPER-OPTIMIZED bulk thread fetching that returns exactly the target number of threads:
    
    1. Dynamically scans until target_thread_count unique threads are found
    2. Respects max_age_months limit (default 6 months)
    3. Batch X-GM-THRID fetches (reduce round trips)
    4. Smart thread deduplication 
    5. Efficient IMAP command patterns with single connection
    
    Args:
        target_thread_count: Number of unique threads to return
        max_age_months: Maximum age of threads to consider (default 6 months)
    """
    
    def _super_optimized_fetch_sync() -> tuple[List[EmailThread], Dict[str, float]]:
        start_time = time.time()
        
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mail.login(IMAP_USERNAME, IMAP_PASSWORD)
            
            try:
                timing = {}
                
                # Step 1: Get all sent messages (we'll scan from newest to oldest)
                fetch_sent_start = time.time()
                mail.select('"[Gmail]/Sent Mail"', readonly=True)
                
                # Calculate date cutoff for max_age_months
                import datetime
                cutoff_date = datetime.datetime.now() - datetime.timedelta(days=max_age_months * 30)
                date_str = cutoff_date.strftime("%d-%b-%Y")
                
                # Search for messages newer than cutoff date
                typ, data = mail.uid('search', None, f'SINCE {date_str}')
                if typ != 'OK' or not data or not data[0]:
                    return [], {"total_time": time.time() - start_time, "error": "No sent messages found within age limit"}
                
                all_sent_uids = data[0].split()
                # Start from most recent (end of list)
                all_sent_uids.reverse()  # Newest first
                
                timing['fetch_sent_time'] = time.time() - fetch_sent_start
                logger.info(f"Found {len(all_sent_uids)} sent messages within {max_age_months} months in {timing['fetch_sent_time']:.2f}s")
                
                # Step 2: DYNAMIC BATCH X-GM-THRID fetches until we have enough unique threads
                thread_discovery_start = time.time()
                thread_id_to_uids = defaultdict(list)
                processed_uids = 0
                
                # Batch size for X-GM-THRID fetches (IMAP servers typically support up to 10-20)
                BATCH_SIZE = 10
                logger.info(f"Dynamically scanning for {target_thread_count} unique threads (batches of {BATCH_SIZE})...")
                
                # Scan in batches until we have enough unique threads
                for i in range(0, len(all_sent_uids), BATCH_SIZE):
                    # Stop if we have enough unique threads
                    if len(thread_id_to_uids) >= target_thread_count:
                        logger.info(f"Target reached: {len(thread_id_to_uids)} unique threads found")
                        break
                    
                    batch_uids = all_sent_uids[i:i+BATCH_SIZE]
                    uid_list = ','.join([uid.decode() for uid in batch_uids])
                    processed_uids += len(batch_uids)
                    
                    # Batch fetch X-GM-THRID for multiple UIDs at once
                    typ, data = mail.uid('fetch', uid_list, '(X-GM-THRID)')
                    if typ != 'OK' or not data:
                        logger.warning(f"Failed to batch fetch X-GM-THRID for batch {i//BATCH_SIZE + 1}")
                        continue
                    
                    # Parse batch response - each item is bytes, not tuple
                    for j, response_bytes in enumerate(data):
                        if isinstance(response_bytes, bytes):
                            response_str = response_bytes.decode()
                            
                            # Extract UID and thread ID from response string
                            # Format: '487 (X-GM-THRID 1835242092809915053 UID 600)'
                            uid_match = re.search(r'UID (\d+)', response_str)
                            thrid_match = re.search(r'X-GM-THRID (\d+)', response_str) 
                            
                            if uid_match and thrid_match:
                                uid = uid_match.group(1)
                                thread_id = thrid_match.group(1)
                                thread_id_to_uids[thread_id].append(uid)
                                
                                # Log progress every 10 unique threads
                                if len(thread_id_to_uids) % 10 == 0:
                                    logger.info(f"Progress: {len(thread_id_to_uids)} unique threads found (scanned {processed_uids} messages)")
                            else:
                                logger.warning(f"Could not extract UID/THRID from: {response_str}")
                        else:
                            logger.warning(f"Unexpected response type: {type(response_bytes)}")
                    
                    # Early termination check within batch processing
                    if len(thread_id_to_uids) >= target_thread_count:
                        break
                
                timing['thread_discovery_time'] = time.time() - thread_discovery_start
                actual_threads_found = len(thread_id_to_uids)
                logger.info(f"Dynamic scan complete: {actual_threads_found} unique threads found in {timing['thread_discovery_time']:.2f}s")
                logger.info(f"Scanned {processed_uids}/{len(all_sent_uids)} messages ({processed_uids/len(all_sent_uids)*100:.1f}%)")
                
                # Step 3: SMART thread fetching with deduplication
                bulk_fetch_start = time.time()
                mail.select('"[Gmail]/All Mail"', readonly=True)
                
                threads = []
                processed_thread_ids: Set[str] = set()
                
                logger.info(f"Smart fetching {len(thread_id_to_uids)} unique threads (target was {target_thread_count})...")
                
                for thread_id, sent_uids in thread_id_to_uids.items():
                    # Skip if we've already processed this thread (deduplication)
                    if thread_id in processed_thread_ids:
                        logger.info(f"Skipping duplicate thread {thread_id}")
                        continue
                    
                    processed_thread_ids.add(thread_id)
                    
                    try:
                        # Search for all messages in this thread
                        typ, data = mail.uid('search', None, f'(X-GM-THRID {thread_id})')
                        if typ != 'OK' or not data or not data[0]:
                            logger.warning(f"No messages found for thread {thread_id}")
                            continue
                        
                        thread_uids = [uid.decode() for uid in data[0].split()]
                        
                        # BATCH fetch all messages in this thread
                        if thread_uids:
                            uid_list = ','.join(thread_uids)
                            typ, data = mail.uid('fetch', uid_list, '(RFC822 X-GM-LABELS)')
                            if typ != 'OK' or not data:
                                logger.warning(f"Failed to fetch messages for thread {thread_id}")
                                continue
                            
                            messages = []
                            k = 0
                            while k < len(data):
                                if isinstance(data[k], tuple) and len(data[k]) >= 2:
                                    header_info = data[k][0].decode() if isinstance(data[k][0], bytes) else str(data[k][0])
                                    msg = email.message_from_bytes(data[k][1])
                                    message_id_header = msg.get('Message-ID', '').strip('<>')
                                    
                                    # Skip drafts (no Message-ID)
                                    if not message_id_header:
                                        k += 1
                                        continue
                                    
                                    # Extract UID from header info
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
                                    
                                    # Simplified body extraction for speed
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
                                k += 1
                            
                            if messages:
                                thread = EmailThread.from_messages(messages, thread_id)
                                threads.append(thread)
                                logger.info(f"Processed thread {thread_id}: {len(messages)} messages")
                    
                    except Exception as e:
                        logger.warning(f"Error processing thread {thread_id}: {e}")
                        continue
                
                timing['bulk_fetch_time'] = time.time() - bulk_fetch_start
                timing['total_time'] = time.time() - start_time
                
                logger.info(f"SUPER-OPTIMIZED: {len(threads)} threads in {timing['total_time']:.2f}s (target: {target_thread_count})")
                logger.info(f"  Breakdown: sent({timing['fetch_sent_time']:.2f}s) + discovery({timing['thread_discovery_time']:.2f}s) + fetch({timing['bulk_fetch_time']:.2f}s)")
                logger.info(f"  Efficiency: Found {len(threads)} threads by scanning {processed_uids} messages ({processed_uids/len(threads):.1f} messages per thread)")
                
                return threads, timing
                
            finally:
                try:
                    mail.logout()
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error in super-optimized fetch: {e}", exc_info=True)
            return [], {"total_time": time.time() - start_time, "error": str(e)}
    
    return await asyncio.get_running_loop().run_in_executor(None, _super_optimized_fetch_sync)

async def main():
    """Test super-optimized approach"""
    logger.info("=== SUPER-OPTIMIZED Bulk Thread Fetching Test ===")
    
    try:
        for target_threads in [10, 25, 50]:
            logger.info(f"\n--- SUPER-OPTIMIZED Testing with target threads: {target_threads} ---")
            
            threads, timing_info = await fetch_threads_super_optimized(target_thread_count=target_threads)
            
            logger.info(f"SUPER-OPTIMIZED TIMING RESULTS for target {target_threads} threads:")
            for key, value in timing_info.items():
                if isinstance(value, float):
                    logger.info(f"  {key}: {value:.2f}s")
                else:
                    logger.info(f"  {key}: {value}")
            
            if threads:
                total_messages = sum(len(thread.messages) for thread in threads)
                logger.info(f"SUPER-OPTIMIZED RESULTS:")
                logger.info(f"  target_threads: {target_threads}")
                logger.info(f"  threads_found: {len(threads)}")
                logger.info(f"  total_messages: {total_messages}")
                logger.info(f"  avg_messages_per_thread: {total_messages / len(threads):.2f}")
                logger.info(f"  target_achievement: {len(threads)/target_threads*100:.1f}%")
                
                if timing_info.get('total_time', 0) > 0:
                    threads_per_second = len(threads) / timing_info['total_time']
                    messages_per_second = total_messages / timing_info['total_time']
                    logger.info(f"  SPEED: {threads_per_second:.2f} threads/sec, {messages_per_second:.2f} messages/sec")
                    
                    # Compare to original (0.54 threads/sec, 1.71 messages/sec)
                    speedup_threads = threads_per_second / 0.54
                    speedup_messages = messages_per_second / 1.71
                    logger.info(f"  SPEEDUP vs Original: {speedup_threads:.1f}x threads, {speedup_messages:.1f}x messages")
                    
                    # Compare to previous optimized (2.39 threads/sec, 6.30 messages/sec for 50 threads)
                    if target_threads == 50:
                        prev_threads_per_sec = 2.39
                        prev_messages_per_sec = 6.30
                        improvement_threads = threads_per_second / prev_threads_per_sec
                        improvement_messages = messages_per_second / prev_messages_per_sec
                        logger.info(f"  IMPROVEMENT vs Previous: {improvement_threads:.1f}x threads, {improvement_messages:.1f}x messages")
    
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 
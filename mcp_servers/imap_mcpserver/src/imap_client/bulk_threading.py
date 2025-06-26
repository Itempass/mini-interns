"""
Bulk thread fetching functionality for IMAP email processing.

This module provides optimized functions for fetching multiple email threads
efficiently using single-connection batching and smart deduplication.
"""

import asyncio
import imaplib
import email
import re
import time
import datetime
import logging
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict

from .models import EmailMessage, EmailThread
from .helpers.contextual_id import create_contextual_id

logger = logging.getLogger(__name__)

def _extract_body_formats(msg) -> Dict[str, str]:
    """Extract body in multiple formats: raw, markdown, and cleaned"""
    html_body = ""
    text_body = ""
    
    # Extract both HTML and plain text if available
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            charset = part.get_content_charset() or 'utf-8'
            
            if content_type == "text/plain" and not text_body:
                try:
                    text_body = part.get_payload(decode=True).decode(charset, errors='ignore')
                except:
                    text_body = str(part.get_payload())
            elif content_type == "text/html" and not html_body:
                try:
                    html_body = part.get_payload(decode=True).decode(charset, errors='ignore')
                except:
                    html_body = str(part.get_payload())
    else:
        charset = msg.get_content_charset() or 'utf-8'
        content = msg.get_payload(decode=True)
        if isinstance(content, bytes):
            try:
                content = content.decode(charset, errors='ignore')
            except:
                content = str(content)
        
        if msg.get_content_type() == "text/html":
            html_body = content
        else:
            text_body = content
    
    # For bulk operations, use simplified body extraction for performance
    raw_body = html_body if html_body else text_body
    markdown_body = text_body if text_body else html_body
    cleaned_body = text_body if text_body else html_body
    
    return {
        'raw': raw_body or "",
        'markdown': markdown_body or "",
        'cleaned': cleaned_body or ""
    }

def _fetch_bulk_threads_sync(
    target_thread_count: int,
    max_age_months: int,
    imap_server: str,
    imap_username: str,
    imap_password: str,
    imap_port: int = 993
) -> Tuple[List[EmailThread], Dict[str, float]]:
    """
    Synchronous implementation of bulk thread fetching.
    
    Args:
        target_thread_count: Number of unique threads to return
        max_age_months: Maximum age of threads to consider (default 6 months)
        imap_server: IMAP server hostname
        imap_username: IMAP username
        imap_password: IMAP password
        imap_port: IMAP port (default 993)
        
    Returns:
        Tuple of (threads_list, timing_dict)
    """
    start_time = time.time()
    
    try:
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(imap_username, imap_password)
        
        try:
            timing = {}
            
            # Step 1: Get all sent messages within age limit
            fetch_sent_start = time.time()
            mail.select('"[Gmail]/Sent Mail"', readonly=True)
            
            # Calculate date cutoff for max_age_months
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
            
            # Step 2: Dynamic batch X-GM-THRID fetches until we have enough unique threads
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
            
            # Step 3: Smart thread fetching with deduplication
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
                    
                    # Batch fetch all messages in this thread
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
                                
                                contextual_id = create_contextual_id('[Gmail]/All Mail', uid)
                                
                                # Extract Gmail labels
                                labels = []
                                labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
                                if labels_match:
                                    labels_str = labels_match.group(1)
                                    labels = re.findall(r'"([^"]*)"', labels_str)
                                    labels = [label.replace('\\\\', '\\') for label in labels]
                                
                                # Extract body formats
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
            
            logger.info(f"BULK THREAD FETCH: {len(threads)} threads in {timing['total_time']:.2f}s (target: {target_thread_count})")
            logger.info(f"  Breakdown: sent({timing['fetch_sent_time']:.2f}s) + discovery({timing['thread_discovery_time']:.2f}s) + fetch({timing['bulk_fetch_time']:.2f}s)")
            logger.info(f"  Efficiency: Found {len(threads)} threads by scanning {processed_uids} messages ({processed_uids/len(threads) if threads else 0:.1f} messages per thread)")
            
            return threads, timing
            
        finally:
            try:
                mail.logout()
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error in bulk thread fetch: {e}", exc_info=True)
        return [], {"total_time": time.time() - start_time, "error": str(e)}

async def fetch_recent_threads_bulk(
    target_thread_count: int = 50,
    max_age_months: int = 6,
    imap_server: str = "imap.gmail.com",
    imap_username: Optional[str] = None,
    imap_password: Optional[str] = None,
    imap_port: int = 993
) -> Tuple[List[EmailThread], Dict[str, float]]:
    """
    Fetch a target number of recent email threads efficiently.
    
    This function uses optimized bulk operations to fetch email threads:
    1. Dynamically scans sent messages until target thread count is reached
    2. Respects max_age_months limit (default 6 months)
    3. Uses batch X-GM-THRID fetches to reduce IMAP round trips
    4. Smart thread deduplication to avoid processing duplicates
    5. Single persistent IMAP connection for optimal performance
    
    Args:
        target_thread_count: Number of unique threads to return (default 50)
        max_age_months: Maximum age of threads to consider in months (default 6)
        imap_server: IMAP server hostname (default "imap.gmail.com")
        imap_username: IMAP username (uses env var if None)
        imap_password: IMAP password (uses env var if None)
        imap_port: IMAP port (default 993)
        
    Returns:
        Tuple of (threads_list, timing_dict) where:
        - threads_list: List of EmailThread objects
        - timing_dict: Dictionary with timing breakdown and metadata
        
    Example:
        threads, timing = await fetch_recent_threads_bulk(target_thread_count=25)
        print(f"Found {len(threads)} threads in {timing['total_time']:.2f}s")
    """
    import os
    
    # Use environment variables if credentials not provided
    if imap_username is None:
        imap_username = os.getenv("IMAP_USERNAME", "arthur@itempass.com")
    if imap_password is None:
        imap_password = os.getenv("IMAP_PASSWORD")
    
    if not imap_password:
        raise ValueError("IMAP password must be provided or set in IMAP_PASSWORD environment variable")
    
    return await asyncio.get_running_loop().run_in_executor(
        None, 
        _fetch_bulk_threads_sync,
        target_thread_count,
        max_age_months,
        imap_server,
        imap_username,
        imap_password,
        imap_port
    ) 
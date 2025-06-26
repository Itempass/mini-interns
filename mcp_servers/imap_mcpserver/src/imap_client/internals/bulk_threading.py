"""
Bulk thread fetching functionality for IMAP email processing.

This module provides optimized functions for fetching multiple email threads
efficiently using single-connection batching and smart deduplication.
"""

from __future__ import annotations
import asyncio
import imaplib
import email
import re
import time
import datetime
import logging
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict
from email_reply_parser import EmailReplyParser
try:
    import html2text
except ImportError:
    html2text = None

from mcp_servers.imap_mcpserver.src.imap_client.models import EmailMessage, EmailThread
from mcp_servers.imap_mcpserver.src.imap_client.helpers.contextual_id import create_contextual_id
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import IMAPConnectionManager, get_default_connection_manager
from mcp_servers.imap_mcpserver.src.imap_client.helpers.body_parser import extract_body_formats

logger = logging.getLogger(__name__)

def _fetch_bulk_threads_sync(
    connection_manager: IMAPConnectionManager,
    target_thread_count: int,
    max_age_months: int,
) -> tuple[list[EmailThread], dict[str, float]]:
    """
    Synchronous implementation of bulk thread fetching.
    
    Args:
        connection_manager: An IMAPConnectionManager instance to handle connections.
        target_thread_count: Number of unique threads to return
        max_age_months: Maximum age of threads to consider (default 6 months)
        
    Returns:
        Tuple of (threads_list, timing_dict)
    """
    start_time = time.time()
    
    try:
        with connection_manager.connect() as mail:
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
                            # The response for a single message can be a tuple (header, body)
                            # or it can be spread across multiple items. We only care about the tuples.
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
                                body_formats = extract_body_formats(msg)
                                
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
            
    except Exception as e:
        logger.error(f"Error in bulk thread fetch: {e}", exc_info=True)
        return [], {"total_time": time.time() - start_time, "error": str(e)}

async def fetch_recent_threads_bulk(
    target_thread_count: int = 50,
    max_age_months: int = 6,
) -> tuple[list[EmailThread], dict[str, float]]:
    """
    Fetch a target number of recent email threads efficiently.
    
    This function uses the default connection manager to fetch email threads
    using optimized bulk operations.
    
    Args:
        target_thread_count: Number of unique threads to return (default 50)
        max_age_months: Maximum age of threads to consider in months (default 6)
        
    Returns:
        Tuple of (threads_list, timing_dict)
    """
    connection_manager = get_default_connection_manager()
    
    return await asyncio.get_running_loop().run_in_executor(
        None, 
        _fetch_bulk_threads_sync,
        connection_manager,
        target_thread_count,
        max_age_months
    ) 
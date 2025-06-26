import asyncio
import logging
import sys
import os
import time
from typing import List, Set, Dict

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from imap_client.client import (
    get_recent_sent_messages, 
    get_complete_thread
)
from imap_client.models import EmailMessage, EmailThread

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_recent_threads_bulk(max_emails_to_scan: int = 50) -> tuple[List[EmailThread], Dict[str, float]]:
    """
    Experiment with bulk thread fetching logic.
    
    Strategy:
    1. Get recent sent messages (they're likely to be part of active conversations)
    2. For each message, get its complete thread
    3. Deduplicate threads by gmail_thread_id
    4. Return unique threads
    
    Returns:
        Tuple of (threads, timing_info)
    """
    start_time = time.time()
    logger.info(f"Starting bulk thread fetch, scanning {max_emails_to_scan} recent sent emails")
    
    # Step 1: Get recent sent messages
    fetch_sent_start = time.time()
    recent_sent = await get_recent_sent_messages(count=max_emails_to_scan)
    fetch_sent_time = time.time() - fetch_sent_start
    logger.info(f"Found {len(recent_sent)} recent sent messages in {fetch_sent_time:.2f}s")
    
    if not recent_sent:
        logger.warning("No recent sent messages found")
        return [], {"total_time": time.time() - start_time, "fetch_sent_time": fetch_sent_time}
    
    # Step 2: Get threads for each message, with deduplication
    thread_fetch_start = time.time()
    seen_thread_ids: Set[str] = set()
    unique_threads: List[EmailThread] = []
    individual_thread_times = []
    
    for i, message in enumerate(recent_sent):
        logger.info(f"Processing message {i+1}/{len(recent_sent)}: {message.subject}")
        
        try:
            thread_start = time.time()
            thread = await get_complete_thread(message)
            thread_time = time.time() - thread_start
            individual_thread_times.append(thread_time)
            
            if thread and thread.thread_id:
                if thread.thread_id not in seen_thread_ids:
                    seen_thread_ids.add(thread.thread_id)
                    unique_threads.append(thread)
                    logger.info(f"Added new thread: {thread.thread_id} with {len(thread.messages)} messages (took {thread_time:.2f}s)")
                else:
                    logger.info(f"Skipping duplicate thread: {thread.thread_id} (took {thread_time:.2f}s)")
            else:
                logger.warning(f"Could not get thread for message: {message.message_id} (took {thread_time:.2f}s)")
                
        except Exception as e:
            logger.error(f"Error getting thread for message {message.message_id}: {e}")
            continue
    
    thread_fetch_time = time.time() - thread_fetch_start
    total_time = time.time() - start_time
    
    timing_info = {
        "total_time": total_time,
        "fetch_sent_time": fetch_sent_time,
        "thread_fetch_time": thread_fetch_time,
        "avg_thread_time": sum(individual_thread_times) / len(individual_thread_times) if individual_thread_times else 0,
        "min_thread_time": min(individual_thread_times) if individual_thread_times else 0,
        "max_thread_time": max(individual_thread_times) if individual_thread_times else 0,
        "messages_processed": len(recent_sent),
        "unique_threads_found": len(unique_threads)
    }
    
    logger.info(f"Bulk fetch complete: {len(unique_threads)} unique threads found in {total_time:.2f}s")
    logger.info(f"Performance: {len(recent_sent)} messages processed, avg {timing_info['avg_thread_time']:.2f}s per thread")
    
    return unique_threads, timing_info

async def analyze_thread_efficiency(threads: List[EmailThread]) -> Dict[str, any]:
    """Analyze the efficiency of our thread fetching"""
    if not threads:
        return {"error": "No threads to analyze"}
    
    total_messages = sum(len(thread.messages) for thread in threads)
    thread_sizes = [len(thread.messages) for thread in threads]
    
    analysis = {
        "total_threads": len(threads),
        "total_messages": total_messages,
        "avg_messages_per_thread": total_messages / len(threads),
        "min_thread_size": min(thread_sizes),
        "max_thread_size": max(thread_sizes),
        "single_message_threads": sum(1 for size in thread_sizes if size == 1),
        "multi_message_threads": sum(1 for size in thread_sizes if size > 1),
    }
    
    return analysis

async def main():
    """Main test function"""
    logger.info("=== Bulk Thread Fetching Experiment ===")
    
    try:
        # Experiment with different batch sizes
        for batch_size in [10, 25, 50]:
            logger.info(f"\n--- Testing with batch size: {batch_size} ---")
            
            threads, timing_info = await fetch_recent_threads_bulk(max_emails_to_scan=batch_size)
            analysis = await analyze_thread_efficiency(threads)
            
            logger.info(f"TIMING RESULTS for batch size {batch_size}:")
            for key, value in timing_info.items():
                if isinstance(value, float):
                    logger.info(f"  {key}: {value:.2f}s")
                else:
                    logger.info(f"  {key}: {value}")
            
            logger.info(f"THREAD ANALYSIS for batch size {batch_size}:")
            for key, value in analysis.items():
                if isinstance(value, float):
                    logger.info(f"  {key}: {value:.2f}")
                else:
                    logger.info(f"  {key}: {value}")
            
            # Show a sample of thread subjects
            if threads:
                logger.info("Sample thread subjects:")
                for i, thread in enumerate(threads[:5]):  # Show first 5
                    logger.info(f"  {i+1}. {thread.subject} ({len(thread.messages)} messages)")
                    
                if len(threads) > 5:
                    logger.info(f"  ... and {len(threads) - 5} more threads")
                    
            # Calculate efficiency metrics
            if timing_info.get('total_time', 0) > 0:
                threads_per_second = len(threads) / timing_info['total_time']
                messages_per_second = analysis.get('total_messages', 0) / timing_info['total_time']
                logger.info(f"EFFICIENCY: {threads_per_second:.2f} threads/sec, {messages_per_second:.2f} messages/sec")
    
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 
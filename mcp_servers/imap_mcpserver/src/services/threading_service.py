"""
A service to handle email threading logic.

This service implements a multi-layered approach to determine the most
efficient way to fetch an email thread from an IMAP server.
"""
import imaplib
import logging
import email
from email.message import Message
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

class ThreadingService:
    """
    Encapsulates the logic for fetching email threads using the best available method.
    """
    def __init__(self, mail: imaplib.IMAP4_SSL):
        self.mail = mail
        self.capabilities: List[str] = self._get_capabilities()

    def _get_capabilities(self) -> List[str]:
        """Fetches and decodes the server's capabilities."""
        typ, data = self.mail.capability()
        if typ == 'OK':
            return [cap.upper() for cap in data[0].decode().split()]
        logger.warning("Could not fetch server capabilities.")
        return []

    def get_thread_uids(self, message_uid: str, current_mailbox: str) -> Tuple[Optional[str], List[str]]:
        """
        Orchestrates fetching thread UIDs using the best available strategy.
        Returns the mailbox where the thread was found and a list of UIDs.
        """
        logger.info(f"Starting thread fetch for UID: {message_uid} from mailbox: {current_mailbox}")
        
        # Layer 1: Try server-side THREAD command
        if 'THREAD=REFERENCES' in self.capabilities:
            logger.info(f"Trying THREAD=REFERENCES for UID {message_uid}.")
            thread_uids = self._thread_with_references(message_uid)
            if thread_uids:
                logger.info(f"Successfully fetched thread for UID {message_uid} using THREAD=REFERENCES.")
                # This command runs on the currently selected mailbox.
                return current_mailbox, thread_uids

        # Layer 2: Try Gmail's X-GM-THRID
        if 'X-GM-EXT-1' in self.capabilities:
            logger.info(f"Trying X-GM-EXT-1 for UID {message_uid}.")
            thread_uids = self._thread_with_gmail_thrid(message_uid)
            if thread_uids:
                logger.info(f"Successfully fetched thread for UID {message_uid} using X-GM-THRID.")
                # Gmail search should happen in All Mail for completeness.
                return '[Gmail]/All Mail', thread_uids
            else:
                # IMPORTANT: If Gmail search fails, it may have polluted the connection state
                # by selecting '[Gmail]/All Mail'. We must reset to the original mailbox.
                logger.warning(f"Gmail search failed. Resetting selected mailbox to '{current_mailbox}'.")
                try:
                    self.mail.select(f'"{current_mailbox}"', readonly=True)
                except imaplib.IMAP4.error as e:
                    logger.error(f"FATAL: Could not reset mailbox to '{current_mailbox}' after failed search. Aborting. Error: {e}")
                    # If we can't even reset, something is very wrong. Return to prevent further errors.
                    return current_mailbox, [message_uid]

        # Layer 3: Fallback to client-side header parsing
        logger.info(f"Falling back to header-based threading for UID {message_uid}.")
        thread_uids = self._thread_with_headers(message_uid)
        if thread_uids:
            logger.info(f"Successfully fetched thread for UID {message_uid} using header parsing.")
            return current_mailbox, thread_uids
        
        logger.warning(f"Could not find thread for UID {message_uid}. Returning single message.")
        return current_mailbox, [message_uid]


    def _thread_with_references(self, message_uid: str) -> Optional[List[str]]:
        """
        Fetches a thread using the IMAP THREAD=REFERENCES algorithm.
        
        This command groups messages by the 'References' header. It's the
        most efficient, standards-based way to thread.
        """
        try:
            # First, find which thread the message belongs to.
            # The server returns a list of threads. Each thread is a space-separated list of UIDs.
            typ, data = self.mail.uid('thread', 'REFERENCES', 'UTF-8', '(UID ' + message_uid + ')')
            if typ != 'OK' or not data or not data[0]:
                logger.warning(f"THREAD=REFERENCES command failed or returned no data for UID {message_uid}.")
                return None
            
            # The response is a list of threads, e.g., [b'(1 2 3) (4 5)']
            # We need to find our UID in this response.
            thread_data = data[0].decode()
            
            # Find the thread containing our message UID
            threads = thread_data.strip()[1:-1].split(') (')
            for thread in threads:
                uids = thread.split()
                if message_uid in uids:
                    logger.info(f"Found thread for UID {message_uid} with {len(uids)} messages.")
                    return uids

            logger.warning(f"Could not find UID {message_uid} in THREAD command response.")
            return None
            
        except imaplib.IMAP4.error as e:
            logger.error(f"Error using THREAD=REFERENCES for UID {message_uid}: {e}", exc_info=True)
            return None

    def _thread_with_gmail_thrid(self, message_uid: str) -> Optional[List[str]]:
        """
        Fetches a thread using Gmail's proprietary X-GM-THRID.
        This implementation now searches '[Gmail]/All Mail' for UIDs.
        """
        try:
            # First, fetch the X-GM-THRID from the specific message in the current mailbox.
            typ, data = self.mail.uid('fetch', message_uid.encode(), '(X-GM-THRID)')
            if typ != 'OK' or not data or not data[0]:
                logger.warning(f"Could not fetch X-GM-THRID for UID {message_uid}.")
                return None
            
            # Response is like: b'1 (X-GM-THRID 17...)'
            thrid_match = email.message_from_bytes(data[0]).get('X-GM-THRID')
            if not thrid_match:
                 # Fallback for different response format
                match = imaplib.re.search(b'X-GM-THRID (\\d+)', data[0])
                if not match:
                    logger.warning(f"Could not parse X-GM-THRID from response for UID {message_uid}")
                    return None
                thrid_match = match.group(1).decode()

            if not thrid_match:
                logger.warning(f"No X-GM-THRID found for UID {message_uid}")
                return None

            gmail_thread_id = thrid_match
            logger.info(f"Found X-GM-THRID: {gmail_thread_id}, searching in '[Gmail]/All Mail'.")

            # Now, search for all UIDs with that thread ID in '[Gmail]/All Mail'.
            try:
                logger.warning(f"Switching to '[Gmail]/All Mail' to search for thread {gmail_thread_id}. This will change the connection's selected mailbox.")
                self.mail.select(mailbox='"[Gmail]/All Mail"', readonly=True)
            except imaplib.IMAP4.error as e:
                logger.error(f"Could not select '[Gmail]/All Mail'. Aborting Gmail-specific search. Error: {e}")
                return None # Fallback to next method in orchestrator.

            # Use Gmail's advanced search to find all messages in the thread, excluding drafts.
            search_query = f'thrid:{gmail_thread_id} -in:drafts'
            typ, data = self.mail.uid('search', None, f'(X-GM-RAW "{search_query}")')

            if typ != 'OK' or not data or not data[0]:
                logger.warning(f"Search for X-GM-THRID {gmail_thread_id} failed in '[Gmail]/All Mail'.")
                return None

            uids = data[0].split()
            return [uid.decode() for uid in uids] if uids else None

        except imaplib.IMAP4.error as e:
            logger.error(f"Error using X-GM-THRID for UID {message_uid}: {e}", exc_info=True)
            return None

    def _thread_with_headers(self, message_uid: str) -> Optional[List[str]]:
        """
        Reconstructs a thread by parsing email headers. This is the fallback method.
        It works by gathering all related Message-IDs from the 'References' and
        'In-Reply-To' headers and then searching for all messages in the thread.
        """
        try:
            initial_msg = self._fetch_raw_message(message_uid)
            if not initial_msg:
                return None

            # Collect all unique message-ids from the headers of the initial email.
            message_ids_in_thread: Set[str] = set()
            
            # Add the initial message's ID
            if initial_msg['Message-ID']:
                message_ids_in_thread.add(initial_msg['Message-ID'].strip())

            # Add IDs from 'References' header
            references = initial_msg.get('References', '')
            for msg_id in references.split():
                message_ids_in_thread.add(msg_id.strip())

            # Add ID from 'In-Reply-To' header
            in_reply_to = initial_msg.get('In-Reply-To')
            if in_reply_to:
                message_ids_in_thread.add(in_reply_to.strip())
            
            if not message_ids_in_thread:
                logger.warning(f"Could not find any Message-IDs in headers for UID {message_uid}.")
                return [message_uid]

            # We now have a set of message-ids that are *part* of the thread.
            # We need to find all emails on the server that belong to this thread.
            # We can't reliably search for all emails whose 'References' contain any of our IDs.
            # A more robust (but still imperfect) approach is to find the "root" message
            # and then search for all messages that reference it.
            # For simplicity here, we will construct a large OR search.
            # NOTE: This can be slow and is not supported by all servers.
            
            search_queries = []
            for msg_id in message_ids_in_thread:
                # Servers are picky about header searches. We try a few common ways.
                search_queries.append(f'(HEADER Message-ID "{msg_id}")')
                search_queries.append(f'(HEADER References "{msg_id}")')
            
            # The initial message is also a key part of the thread.
            # Let's find messages that *refer* to our initial message.
            initial_msg_id = initial_msg.get('Message-ID')
            if initial_msg_id:
                 search_queries.append(f'(HEADER References "{initial_msg_id.strip()}")')

            # We need to de-duplicate and build the final query
            unique_queries = list(set(search_queries))
            
            if not unique_queries:
                search_query = ""
            elif len(unique_queries) == 1:
                search_query = unique_queries[0]
            else:
                search_query = f"(OR {unique_queries[0]} {unique_queries[1]})"
                for i in range(2, len(unique_queries)):
                    search_query = f"(OR {search_query} {unique_queries[i]})"

            if not search_query:
                return [message_uid]
                
            typ, data = self.mail.uid('search', None, search_query)

            if typ != 'OK' or not data or not data[0]:
                logger.warning(f"Header-based search found no UIDs for query based on UID {message_uid}")
                # If the complex search fails, just return the original email
                return [message_uid]

            uids = list(set(data[0].split())) # Deduplicate UIDs
            decoded_uids = [uid.decode() for uid in uids]
            
            # Ensure the original UID is in the list
            if message_uid not in decoded_uids:
                decoded_uids.append(message_uid)

            logger.info(f"Header search found {len(decoded_uids)} potential thread messages for UID {message_uid}.")
            return decoded_uids

        except Exception as e:
            logger.error(f"Error reconstructing thread with headers for UID {message_uid}: {e}", exc_info=True)
            return None

    def _fetch_raw_message(self, uid: str) -> Optional[Message]:
        """
        Fetches a single raw email message.
        """
        typ, data = self.mail.uid('fetch', uid.encode(), '(RFC822)')
        if typ == 'OK' and data and data[0] is not None:
            for response_part in data:
                if isinstance(response_part, tuple):
                    return email.message_from_bytes(response_part[1])
        logger.warning(f"Failed to fetch raw message for UID {uid}")
        return None 
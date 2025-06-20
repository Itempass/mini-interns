"""
IMAP Service for handling email operations.

This service encapsulates the logic for interacting with an IMAP server,
using credentials loaded from the shared AppSettings.
"""
import asyncio
import email
import imaplib
import logging
from email.header import decode_header
from shared.app_settings import load_app_settings, AppSettings
from typing import Any, Dict, List, Optional
from ..types.imap_models import RawEmail
from .threading_service import ThreadingService
from ..utils.contextual_id import create_contextual_id, parse_contextual_id

logger = logging.getLogger(__name__)

class IMAPService:
    """
    A service class for interacting with an IMAP email server.
    """
    def __init__(self):
        self.settings: AppSettings = load_app_settings()
        self.mail: Optional[imaplib.IMAP4_SSL] = None

    def connect(self) -> None:
        """
        Connects to the IMAP server and logs in.
        """
        if not self.settings.IMAP_SERVER or not self.settings.IMAP_USERNAME or not self.settings.IMAP_PASSWORD:
            logger.error("IMAP settings are not configured. Cannot connect.")
            raise ValueError("IMAP settings (server, username, password) are not fully configured.")
        
        try:
            logger.info(f"Connecting to IMAP server: {self.settings.IMAP_SERVER}")
            self.mail = imaplib.IMAP4_SSL(self.settings.IMAP_SERVER)
            self.mail.login(self.settings.IMAP_USERNAME, self.settings.IMAP_PASSWORD)
            logger.info("IMAP login successful.")
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP connection failed: {e}", exc_info=True)
            self.mail = None
            raise ConnectionError(f"Failed to connect to IMAP server: {e}") from e

    def disconnect(self) -> None:
        """
        Logs out and closes the connection to the IMAP server.
        """
        if self.mail:
            try:
                self.mail.logout()
                logger.info("IMAP logout successful.")
            except imaplib.IMAP4.error as e:
                logger.warning(f"IMAP logout failed, possibly already disconnected: {e}")
            finally:
                self.mail = None

    # --- Placeholder methods for tool implementations ---
    # These will be implemented later to provide the functionality
    # needed by the tools in tools/imap.py

    async def list_inbox_emails(self, max_results: int = 10) -> List[RawEmail]:
        if not self.mail:
            try:
                await asyncio.get_running_loop().run_in_executor(None, self.connect)
            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed: {e}")
                return []
        
        if not self.mail:
            logger.error("IMAP service is not connected.")
            return []

        def _fetch_emails() -> List[RawEmail]:
            try:
                self.mail.select('inbox', readonly=True)
                typ, data = self.mail.uid('search', None, 'ALL')
                if typ != 'OK':
                    logger.error("Failed to search inbox for UIDs.")
                    return []
                
                email_uids = data[0].split()
                if not email_uids:
                    return []

                latest_email_uids = email_uids[-max_results:]
                
                emails: List[RawEmail] = []
                for uid in reversed(latest_email_uids):
                    typ, data = self.mail.uid('fetch', uid, '(RFC822)')
                    if typ != 'OK':
                        logger.warning(f"Failed to fetch email with UID {uid.decode()}")
                        continue

                    for response_part in data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            contextual_id = create_contextual_id('inbox', uid.decode())
                            emails.append(RawEmail(uid=contextual_id, msg=msg))
                return emails
            except imaplib.IMAP4.error as e:
                logger.error(f"Error fetching emails with UIDs: {e}", exc_info=True)
                # Connection might be stale, try to disconnect.
                self.disconnect() # disconnect is blocking
                return []

        return await asyncio.get_running_loop().run_in_executor(None, _fetch_emails)

    async def get_email(self, message_id: str) -> Optional[RawEmail]:
        """
        Retrieves a specific email by its contextual ID.
        """
        if not self.mail:
            try:
                await asyncio.get_running_loop().run_in_executor(None, self.connect)
            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed: {e}")
                return None
        
        if not self.mail:
            logger.error("IMAP service is not connected.")
            return None

        def _fetch_email() -> Optional[RawEmail]:
            try:
                mailbox, uid = parse_contextual_id(message_id)
                self.mail.select(mailbox, readonly=True)
                
                typ, data = self.mail.uid('fetch', uid.encode('utf-8'), '(RFC822)')

                if typ != 'OK' or not data or data[0] is None:
                    logger.warning(f"Failed to fetch email with UID {uid} from mailbox {mailbox}")
                    return None

                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        # Return the original contextual ID for consistency
                        return RawEmail(uid=message_id, msg=msg)
                
                logger.warning(f"Could not parse email content for UID {uid} from mailbox {mailbox}")
                return None

            except imaplib.IMAP4.error as e:
                logger.error(f"Error fetching email with contextual ID {message_id}: {e}", exc_info=True)
                self.disconnect()
                return None

        return await asyncio.get_running_loop().run_in_executor(None, _fetch_email)

    async def fetch_email_thread(self, message_id: str) -> List[RawEmail]:
        """
        Fetches an entire email thread using the best available method.
        """
        if not self.mail:
            try:
                await asyncio.get_running_loop().run_in_executor(None, self.connect)
            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed: {e}")
                return []
        
        if not self.mail:
            logger.error("IMAP service is not connected.")
            return []

        def _fetch_thread() -> List[RawEmail]:
            try:
                # The threading service needs to start from a specific email.
                # We select the initial mailbox before calling it.
                initial_mailbox, initial_uid = parse_contextual_id(message_id)
                self.mail.select(initial_mailbox, readonly=True)
                
                threading_service = ThreadingService(self.mail)
                thread_mailbox, thread_uids = threading_service.get_thread_uids(initial_uid)

                if not thread_uids:
                    return []

                emails: List[RawEmail] = []
                # After getting the UIDs, we must select the correct mailbox they belong to.
                self.mail.select(thread_mailbox, readonly=True)
                
                for uid in thread_uids:
                    typ, data = self.mail.uid('fetch', uid.encode('utf-8'), '(RFC822)')
                    if typ == 'OK' and data and data[0] is not None:
                        for response_part in data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                contextual_id = create_contextual_id(thread_mailbox, uid)
                                emails.append(RawEmail(uid=contextual_id, msg=msg))
                                break
                    else:
                        logger.warning(f"Failed to fetch email with UID {uid} from {thread_mailbox}.")

                return emails

            except imaplib.IMAP4.error as e:
                logger.error(f"Error fetching email thread for contextual ID {message_id}: {e}", exc_info=True)
                self.disconnect()
                return []

        return await asyncio.get_running_loop().run_in_executor(None, _fetch_thread)

    async def search_emails(self, query: str, max_results: int = 10):
        # Placeholder for searching emails
        pass

    async def draft_reply(self, message_id: str, body: str, cc: list = None, bcc: list = None):
        # Placeholder for drafting a reply
        pass 
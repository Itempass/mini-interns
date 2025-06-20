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

    def _format_email_as_markdown(self, msg: email.message.Message, email_id: str) -> str:
        def _decode_header(header_value: str) -> str:
            if not header_value:
                return ""
            parts = decode_header(header_value)
            header_parts = []
            for part, encoding in parts:
                if isinstance(part, bytes):
                    header_parts.append(part.decode(encoding or 'utf-8', errors='ignore'))
                else:
                    header_parts.append(str(part))
            return "".join(header_parts)

        subject = _decode_header(msg['subject'])
        from_ = _decode_header(msg['from'])
        to = _decode_header(msg.get('to'))
        cc = _decode_header(msg.get('cc'))
        date = msg.get('date', 'N/A')

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(charset, errors='ignore')
                            break
                    except Exception as e:
                        logger.warning(f"Could not decode body part for email id {email_id}: {e}")
                        body = "[Could not decode body]"
        else:
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(charset, errors='ignore')
            except Exception as e:
                logger.warning(f"Could not decode body for email id {email_id}: {e}")
                body = "[Could not decode body]"

        return (
            f"## Subject: {subject}\n"
            f"* id: {email_id}\n"
            f"* from: {from_}\n"
            f"* to: {to or 'N/A'}\n"
            f"* cc: {cc or 'N/A'}\n"
            f"* date: {date}\n\n"
            f"{body.strip()}"
        )

    async def list_inbox_emails(self, max_results: int = 10) -> List[str]:
        if not self.mail:
            try:
                await asyncio.get_running_loop().run_in_executor(None, self.connect)
            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed: {e}")
                return []
        
        if not self.mail:
            logger.error("IMAP service is not connected.")
            return []

        def _fetch_emails() -> List[str]:
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
                
                emails: List[str] = []
                for uid in reversed(latest_email_uids):
                    typ, data = self.mail.uid('fetch', uid, '(RFC822)')
                    if typ != 'OK':
                        logger.warning(f"Failed to fetch email with UID {uid.decode()}")
                        continue

                    for response_part in data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            markdown_email = self._format_email_as_markdown(msg, uid.decode())
                            emails.append(markdown_email)
                return emails
            except imaplib.IMAP4.error as e:
                logger.error(f"Error fetching emails with UIDs: {e}", exc_info=True)
                # Connection might be stale, try to disconnect.
                self.disconnect() # disconnect is blocking
                return []

        return await asyncio.get_running_loop().run_in_executor(None, _fetch_emails)

    async def get_email(self, message_id: str):
        # Placeholder for getting a specific email
        pass

    async def search_emails(self, query: str, max_results: int = 10):
        # Placeholder for searching emails
        pass

    async def draft_reply(self, message_id: str, body: str, cc: list = None, bcc: list = None):
        # Placeholder for drafting a reply
        pass 
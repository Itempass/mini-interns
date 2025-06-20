"""
IMAP Service for handling email operations.

This service encapsulates the logic for interacting with an IMAP server,
using credentials loaded from the shared AppSettings.
"""
import asyncio
import email
import imaplib
import logging
import re
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import email.utils
from shared.app_settings import load_app_settings, AppSettings
from typing import Any, Dict, List, Optional
from ..types.imap_models import RawEmail
from .threading_service import ThreadingService
from ..utils.contextual_id import create_contextual_id, parse_contextual_id

logger = logging.getLogger(__name__)

def _markdown_to_html(markdown_text: str) -> str:
    """
    Convert markdown formatting to HTML.
    """
    html = markdown_text
    # Bold text (**text** or __text__)
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__(.*?)__', r'<strong>\1</strong>', html)
    # Italic text (*text* or _text_)
    html = re.sub(r'(?<!\*)\*(?!\*)([^*]+)\*(?!\*)', r'<em>\1</em>', html)
    html = re.sub(r'(?<!_)_(?!_)([^_]+)_(?!_)', r'<em>\1</em>', html)
    # Links [text](url)
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
    # Headers
    html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    # Blockquotes
    html = re.sub(r'^> (.*?)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)
    # Code blocks ```
    html = re.sub(r'```(.*?)```', r'<pre><code>\1</code></pre>', html, flags=re.DOTALL)
    # Line breaks
    html = html.replace('\n', '<br>\n')
    return html

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

    def _find_drafts_folder(self) -> str:
        """
        Find the correct drafts folder name by trying common variations.
        """
        draft_folders = ["[Gmail]/Drafts", "DRAFTS", "Drafts", "[Google Mail]/Drafts"]
        selected_folder = None
        
        try:
            status, folders = self.mail.list()
            if status == "OK":
                folder_list = [
                    folder.decode().split('"')[-2] if '"' in folder.decode() else folder.decode().split()[-1]
                    for folder in folders
                ]
                logger.info(f"Available folders: {folder_list}")
                for draft_folder in draft_folders:
                    if draft_folder in folder_list:
                        selected_folder = draft_folder
                        logger.info(f"Found drafts folder: {selected_folder}")
                        break
                if not selected_folder:
                    for folder_name in folder_list:
                        if "draft" in folder_name.lower():
                            selected_folder = folder_name
                            logger.info(f"Found drafts folder by search: {selected_folder}")
                            break
        except Exception as e:
            logger.warning(f"Error listing folders: {e}")
        
        if not selected_folder:
            selected_folder = "[Gmail]/Drafts"
            logger.info(f"Using default drafts folder: {selected_folder}")
            
        return selected_folder

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

    async def draft_reply(self, message_id: str, body: str) -> Dict[str, Any]:
        if not self.mail:
            try:
                await asyncio.get_running_loop().run_in_executor(None, self.connect)
            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed: {e}")
                return {"success": False, "message": str(e)}

        if not self.mail:
            logger.error("IMAP service is not connected.")
            return {"success": False, "message": "IMAP service is not connected."}

        def _create_and_save_draft() -> Dict[str, Any]:
            try:
                # 1. Fetch the original email
                original_raw_email = self.get_email_sync(message_id)
                if not original_raw_email:
                    return {"success": False, "message": f"Email with ID {message_id} not found."}
                original_msg = original_raw_email.msg

                # 2. Prepare reply headers
                original_subject = "".join(
                    part.decode(encoding or 'utf-8') if isinstance(part, bytes) else part
                    for part, encoding in decode_header(original_msg['Subject'] or "(No Subject)")
                )
                reply_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"

                # Use Reply-To header if available, otherwise From
                reply_to_header = original_msg.get('Reply-To') or original_msg['From']
                to_email = email.utils.parseaddr(reply_to_header)[1]

                # 3. Create the reply message
                reply_message = MIMEMultipart("alternative")
                reply_message["Subject"] = reply_subject
                reply_message["From"] = self.settings.IMAP_USERNAME
                reply_message["To"] = to_email
                
                original_cc = original_msg.get('Cc')
                logger.info(f"Original email Cc: {original_cc}")
                if original_cc:
                    # getaddresses returns a list of (realname, email-address) tuples
                    cc_emails = [
                        email_address for _, email_address 
                        in email.utils.getaddresses([original_cc]) 
                        if email_address
                    ]
                    logger.info(f"Parsed Cc emails: {cc_emails}")
                    if cc_emails:
                        reply_message['Cc'] = ', '.join(cc_emails)
                        logger.info(f"Set Cc header on reply to: {reply_message['Cc']}")
                else:
                    logger.info("No Cc header found in the original email.")
                
                # Add threading headers
                if original_msg.get('Message-ID'):
                    reply_message["In-Reply-To"] = original_msg.get('Message-ID')
                    reply_message["References"] = original_msg.get('Message-ID')
                
                reply_message["Date"] = email.utils.formatdate(localtime=True)

                # 4. Create body parts
                part1 = MIMEText(body, "plain")
                part2 = MIMEText(_markdown_to_html(body), "html")
                reply_message.attach(part1)
                reply_message.attach(part2)

                # 5. Find drafts folder and save
                drafts_folder = self._find_drafts_folder()
                logger.info(f"Saving draft reply to folder: {drafts_folder}")
                
                message_string = reply_message.as_string()
                result = self.mail.append(drafts_folder, None, None, message_string.encode("utf-8"))

                if result[0] == "OK":
                    return {"success": True, "message": f"Draft reply saved to {drafts_folder}."}
                else:
                    error_msg = f"Error creating draft reply: {result[1][0].decode() if result[1] else 'Unknown error'}"
                    logger.error(error_msg)
                    return {"success": False, "message": error_msg}

            except Exception as e:
                error_msg = f"Error creating draft reply: {str(e)}"
                logger.error(error_msg, exc_info=True)
                # Disconnect on critical error
                self.disconnect()
                return {"success": False, "message": error_msg}

        # Need a synchronous version of get_email for the executor
        def _fetch_email_sync(sync_message_id: str) -> Optional[RawEmail]:
            try:
                mailbox, uid = parse_contextual_id(sync_message_id)
                self.mail.select(mailbox, readonly=True)
                typ, data = self.mail.uid('fetch', uid.encode('utf-8'), '(RFC822)')
                if typ != 'OK' or not data or data[0] is None:
                    return None
                for response_part in data:
                    if isinstance(response_part, tuple):
                        return RawEmail(uid=sync_message_id, msg=email.message_from_bytes(response_part[1]))
                return None
            except imaplib.IMAP4.error:
                return None
        
        self.get_email_sync = _fetch_email_sync
        
        return await asyncio.get_running_loop().run_in_executor(None, _create_and_save_draft) 
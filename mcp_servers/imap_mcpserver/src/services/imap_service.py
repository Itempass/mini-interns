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
from collections import Counter
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import email.utils
from email_reply_parser import EmailReplyParser
import functools
from bs4 import BeautifulSoup
from shared.app_settings import load_app_settings, AppSettings
from typing import Any, Dict, List, Optional, Tuple, Generator
from ..types.imap_models import RawEmail
from .threading_service import ThreadingService
from ..utils.contextual_id import create_contextual_id, parse_contextual_id
import contextlib

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
    Each method call creates a new, isolated connection to ensure thread safety.
    """
    def __init__(self):
        self.settings: AppSettings = load_app_settings()

    @contextlib.contextmanager
    def _connect(self) -> Generator[imaplib.IMAP4_SSL, None, None]:
        """
        Connects to the IMAP server, logs in, and yields the connection.
        Ensures logout and connection closure.
        """
        if not self.settings.IMAP_SERVER or not self.settings.IMAP_USERNAME or not self.settings.IMAP_PASSWORD:
            logger.error("IMAP settings are not configured. Cannot connect.")
            raise ValueError("IMAP settings (server, username, password) are not fully configured.")
        
        mail = None
        try:
            logger.info(f"Connecting to IMAP server: {self.settings.IMAP_SERVER}")
            mail = imaplib.IMAP4_SSL(self.settings.IMAP_SERVER)
            mail.login(self.settings.IMAP_USERNAME, self.settings.IMAP_PASSWORD)
            logger.info("IMAP login successful.")
            yield mail
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP connection failed: {e}", exc_info=True)
            raise ConnectionError(f"Failed to connect to IMAP server: {e}") from e
        finally:
            if mail:
                try:
                    mail.logout()
                    logger.info("IMAP logout successful.")
                except imaplib.IMAP4.error as e:
                    logger.warning(f"IMAP logout failed, possibly already disconnected: {e}")

    def _find_drafts_folder(self, mail: imaplib.IMAP4_SSL) -> str:
        """
        Find the correct drafts folder name by trying common variations.
        """
        draft_folders = ["[Gmail]/Drafts", "DRAFTS", "Drafts", "[Google Mail]/Drafts"]
        selected_folder = None
        
        try:
            status, folders = mail.list()
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

    def _find_sent_folder(self, mail: imaplib.IMAP4_SSL) -> str:
        """
        Find the correct sent folder name by trying common variations.
        """
        sent_folders = ["[Gmail]/Sent Mail", "Sent", "Sent Items"]
        selected_folder = None
        
        try:
            status, folders = mail.list()
            if status == "OK":
                folder_list = [
                    folder.decode().split('"')[-2] if '"' in folder.decode() else folder.decode().split()[-1]
                    for folder in folders
                ]
                logger.info(f"Available folders: {folder_list}")
                for sent_folder in sent_folders:
                    if sent_folder in folder_list:
                        selected_folder = sent_folder
                        logger.info(f"Found sent folder: {selected_folder}")
                        break
                if not selected_folder:
                    for folder_name in folder_list:
                        if "sent" in folder_name.lower():
                            selected_folder = folder_name
                            logger.info(f"Found sent folder by search: {selected_folder}")
                            break
        except Exception as e:
            logger.warning(f"Error listing folders: {e}")
        
        if not selected_folder:
            selected_folder = "[Gmail]/Sent Mail"
            logger.info(f"Using default sent folder: {selected_folder}")
            
        return selected_folder

    @staticmethod
    def _find_best_signature(email_bodies: List[Dict[str, str]]) -> Tuple[Optional[str], Optional[str]]:
        """
        Analyzes a list of email bodies to find the most common plain text and HTML signatures.
        """
        logger.info(f"Starting signature detection for {len(email_bodies)} emails.")
        # --- Part 1: Determine Plain Text Signature ---
        plain_replies = []
        for b in email_bodies:
            if b.get('text'):
                # By reconstructing from fragments, we can keep the signature while removing quoted replies.
                email_message = EmailReplyParser.read(b['text'])
                content_with_signature = "\n".join([f.content for f in email_message.fragments if not f.quoted])
                plain_replies.append(content_with_signature.strip())
        logger.info(f"Plain replies for signature detection (quotes removed): {plain_replies}")

        if len(plain_replies) < 2:
            logger.info("Not enough sent emails with content to determine a signature pattern.")
            return None, None

        best_plain_signature = ""
        last_plain_score = -1
        
        for line_count in range(2, 11): # Check for signatures from 2 to 10 lines long
            logger.info(f"Checking for signatures with {line_count} lines.")
            candidates = [ "\n".join(reply.splitlines()[-line_count:]) for reply in plain_replies if len(reply.splitlines()) >= line_count]
            if not candidates:
                logger.info("No candidates found for this line count.")
                continue
            
            logger.info(f"Candidates for {line_count} lines: {candidates}")
            most_common_candidate, _ = Counter(candidates).most_common(1)[0]
            current_score = sum(1 for reply in plain_replies if reply.endswith(most_common_candidate))
            logger.info(f"Most common candidate: '{most_common_candidate}' with score: {current_score}")

            if current_score < last_plain_score:
                logger.info("Score is lower than the last score. Breaking loop.")
                break
            
            best_plain_signature = most_common_candidate
            last_plain_score = current_score
            logger.info(f"Updating best_plain_signature to: '{best_plain_signature}'")
            if current_score < 2:
                logger.info("Score is less than 2. Breaking loop.")
                break
        
        final_plain_signature = None
        if last_plain_score >= 2:
            final_plain_signature = best_plain_signature.strip()
            logger.info(f"Final confirmed plain-text signature (Score: {last_plain_score}): '{final_plain_signature}'")
        else:
            logger.info("No consistent plain-text signature pattern found.")
            return None, None

        # --- Part 2: Determine HTML Signature ---
        # Use the plain text signature to find "golden" emails that definitely contain a signature.
        golden_emails = []
        for b in email_bodies:
            if b.get('html') and b.get('text'):
                email_message = EmailReplyParser.read(b['text'])
                content_with_signature = "\n".join([f.content for f in email_message.fragments if not f.quoted])
                if content_with_signature.strip().endswith(final_plain_signature):
                    golden_emails.append(b)

        logger.info(f"Found {len(golden_emails)} golden emails to check for an HTML signature.")

        if len(golden_emails) < 2:
            return final_plain_signature, None

        # Parse all golden emails with BeautifulSoup
        parsed_bodies = [BeautifulSoup(email['html'], 'lxml') for email in golden_emails]

        # New approach: Find the plain-text signature in the HTML and walk up the tree
        # to find the common parent.
        signature_parents = []
        for soup in parsed_bodies:
            # Find all text nodes that contain parts of the signature
            signature_lines = [line for line in final_plain_signature.split('\n') if line.strip()]
            text_nodes = []
            for line in signature_lines:
                # Find all text nodes that contain the line, using regex to be flexible with whitespace
                nodes = soup.find_all(string=re.compile(re.escape(line.strip())))
                if nodes:
                    text_nodes.extend(nodes)
            
            if not text_nodes:
                logger.info(f"Signature text not found in HTML body.")
                continue

            # Find the common ancestor of all the found text nodes.
            common_ancestor = text_nodes[0].find_parent()
            for i in range(1, len(text_nodes)):
                ancestor = text_nodes[i].find_parent()
                while common_ancestor not in ancestor.parents and common_ancestor != ancestor:
                    common_ancestor = common_ancestor.find_parent()
                    if not common_ancestor: # Reached the top of the document
                        break
                if not common_ancestor:
                    break # Should not happen if signature is in one block
            
            if common_ancestor:
                signature_parents.append(common_ancestor)

        logger.info(f"Found {len(signature_parents)} potential HTML signature parent blocks.")

        if not signature_parents:
            logger.info("Could not find common HTML parent for signature.")
            return final_plain_signature, None

        # Now, find the most common parent structure.
        # We serialize the parent to a string to make it hashable for Counter.
        parent_strings = [str(p) for p in signature_parents]
        if not parent_strings:
            return final_plain_signature, None

        most_common_html_str, count = Counter(parent_strings).most_common(1)[0]
        logger.info(f"Most common HTML signature candidate: '{most_common_html_str[:150]}...' with count: {count}")
        
        final_html_signature = None
        if count >= 2:
            final_html_signature = most_common_html_str.strip()
            logger.info(f"Final confirmed HTML signature (Score: {count}): '{final_html_signature[:150]}...'")
        else:
            logger.info("No consistent HTML signature pattern found.")

        return final_plain_signature, final_html_signature

    @functools.lru_cache(maxsize=1)
    def get_user_signature(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetches the user's email signature by analyzing the last 10 sent emails.
        It determines the plain text signature first, then uses that to find the
        corresponding HTML signature.
        The result is cached. This method is synchronous and self-contained.
        """
        logger.info("Attempting to determine user signature from sent emails.")
        try:
            with self._connect() as mail:
                sent_folder = self._find_sent_folder(mail)
                try:
                    status, _ = mail.select(f'"{sent_folder}"')
                    if status != 'OK':
                        logger.error(f"Failed to select sent folder '{sent_folder}'.")
                        return None, None
                    
                    typ, data = mail.uid('search', None, 'ALL')
                    if typ != 'OK':
                        logger.error(f"Failed to search sent folder '{sent_folder}'.")
                        return None, None
                    
                    email_uids = data[0].split()
                    if not email_uids:
                        logger.info("No emails found in sent folder.")
                        return None, None

                    latest_email_uids = email_uids[-10:]
                    logger.info(f"Analyzing last {len(latest_email_uids)} emails for signature.")
                    
                    email_bodies = []
                    for uid in latest_email_uids:
                        typ, data = mail.uid('fetch', uid, '(RFC822)')
                        if typ != 'OK':
                            logger.warning(f"Failed to fetch email with UID {uid.decode()}.")
                            continue

                        for response_part in data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                plain_body = ""
                                html_body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        ctype = part.get_content_type()
                                        cdisp = str(part.get('Content-Disposition'))
                                        if ctype == 'text/plain' and 'attachment' not in cdisp:
                                            plain_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                                        elif ctype == 'text/html' and 'attachment' not in cdisp:
                                            html_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                                else:
                                    plain_body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='ignore')
                                
                                if plain_body:
                                    email_bodies.append({'text': plain_body, 'html': html_body})

                    return self._find_best_signature(email_bodies)

                except Exception as e:
                    logger.error(f"An unexpected error occurred while getting user signature: {e}", exc_info=True)
                    return None, None
        except (ValueError, ConnectionError) as e:
            logger.error(f"IMAP connection failed during get_user_signature: {e}")
            return None, None

    # --- Placeholder methods for tool implementations ---
    # These will be implemented later to provide the functionality
    # needed by the tools in tools/imap.py

    async def list_inbox_emails(self, max_results: int = 10) -> List[RawEmail]:
        def _fetch_emails() -> List[RawEmail]:
            try:
                with self._connect() as mail:
                    mail.select('inbox', readonly=True)
                    typ, data = mail.uid('search', None, 'ALL')
                    if typ != 'OK':
                        logger.error("Failed to search inbox for UIDs.")
                        return []
                    
                    email_uids = data[0].split()
                    if not email_uids:
                        return []

                    latest_email_uids = email_uids[-max_results:]
                    
                    emails: List[RawEmail] = []
                    for uid in reversed(latest_email_uids):
                        typ, data = mail.uid('fetch', uid, '(RFC822)')
                        if typ != 'OK':
                            logger.warning(f"Failed to fetch email with UID {uid.decode()}")
                            continue

                        for response_part in data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                contextual_id = create_contextual_id('inbox', uid.decode())
                                emails.append(RawEmail(uid=contextual_id, msg=msg))
                    return emails
            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed during list_inbox_emails: {e}")
                return []
            except imaplib.IMAP4.error as e:
                logger.error(f"Error fetching emails with UIDs: {e}", exc_info=True)
                return []

        return await asyncio.get_running_loop().run_in_executor(None, _fetch_emails)

    async def list_sent_emails(self, max_results: int = 100) -> List[RawEmail]:
        def _fetch_emails() -> List[RawEmail]:
            try:
                with self._connect() as mail:
                    sent_folder = self._find_sent_folder(mail)
                    mail.select(f'"{sent_folder}"', readonly=True)
                    typ, data = mail.uid('search', None, 'ALL')
                    if typ != 'OK':
                        logger.error(f"Failed to search sent folder '{sent_folder}' for UIDs.")
                        return []
                    
                    email_uids = data[0].split()
                    if not email_uids:
                        return []

                    latest_email_uids = email_uids[-max_results:]
                    
                    emails: List[RawEmail] = []
                    for uid in reversed(latest_email_uids):
                        typ, data = mail.uid('fetch', uid, '(RFC822)')
                        if typ != 'OK':
                            logger.warning(f"Failed to fetch email with UID {uid.decode()} from sent folder")
                            continue

                        for response_part in data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                contextual_id = create_contextual_id(sent_folder, uid.decode())
                                emails.append(RawEmail(uid=contextual_id, msg=msg))
                    return emails
            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed during list_sent_emails: {e}")
                return []
            except imaplib.IMAP4.error as e:
                logger.error(f"Error fetching sent emails: {e}", exc_info=True)
                return []

        return await asyncio.get_running_loop().run_in_executor(None, _fetch_emails)

    async def get_email(self, message_id: str) -> Optional[RawEmail]:
        """
        Retrieves a specific email by its contextual ID.
        """
        def _fetch_email() -> Optional[RawEmail]:
            try:
                with self._connect() as mail:
                    mailbox, uid = parse_contextual_id(message_id)
                    mail.select(f'"{mailbox}"', readonly=True)
                    
                    typ, data = mail.uid('fetch', uid.encode('utf-8'), '(RFC822)')

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
            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed during get_email: {e}")
                return None
            except imaplib.IMAP4.error as e:
                logger.error(f"Error fetching email with contextual ID {message_id}: {e}", exc_info=True)
                return None

        return await asyncio.get_running_loop().run_in_executor(None, _fetch_email)

    async def fetch_email_thread(self, message_id: str) -> List[RawEmail]:
        """
        Fetches an entire email thread using the best available method.
        """
        def _fetch_thread() -> List[RawEmail]:
            try:
                with self._connect() as mail:
                    # The threading service needs to start from a specific email.
                    # We select the initial mailbox before calling it.
                    initial_mailbox, initial_uid = parse_contextual_id(message_id)
                    mail.select(f'"{initial_mailbox}"', readonly=True)
                    
                    threading_service = ThreadingService(mail)
                    thread_mailbox, thread_uids = threading_service.get_thread_uids(initial_uid)

                    if not thread_uids:
                        return []

                    emails: List[RawEmail] = []
                    # After getting the UIDs, we must select the correct mailbox they belong to.
                    mail.select(f'"{thread_mailbox}"', readonly=True)
                    
                    for uid in thread_uids:
                        typ, data = mail.uid('fetch', uid.encode('utf-8'), '(RFC822)')
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
            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed during fetch_email_thread: {e}")
                return []
            except imaplib.IMAP4.error as e:
                logger.error(f"Error fetching email thread for contextual ID {message_id}: {e}", exc_info=True)
                return []

        return await asyncio.get_running_loop().run_in_executor(None, _fetch_thread)

    async def search_emails(self, query: str, max_results: int = 10):
        # Placeholder for searching emails
        pass

    async def draft_reply(self, message_id: str, body: str) -> Dict[str, Any]:
        def _get_email_sync(sync_message_id: str, mail: imaplib.IMAP4_SSL) -> Optional[RawEmail]:
            try:
                mailbox, uid = parse_contextual_id(sync_message_id)
                mail.select(f'"{mailbox}"', readonly=True)
                typ, data = mail.uid('fetch', uid.encode('utf-8'), '(RFC822)')
                if typ != 'OK' or not data or data[0] is None:
                    return None
                for response_part in data:
                    if isinstance(response_part, tuple):
                        return RawEmail(uid=sync_message_id, msg=email.message_from_bytes(response_part[1]))
                return None
            except imaplib.IMAP4.error:
                return None

        def _create_and_save_draft() -> Dict[str, Any]:
            try:
                with self._connect() as mail:
                    # 1. Fetch the original email
                    original_raw_email = _get_email_sync(message_id, mail)
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

                    # 4. Get signature and append to body
                    # This call is cached after the first run
                    plain_signature, html_signature = self.get_user_signature()

                    # Prepare plain part
                    full_plain_body = body
                    if plain_signature:
                        full_plain_body = f"{body}\\n\\n{plain_signature}"

                    # Prepare HTML part
                    html_body = _markdown_to_html(body)
                    if html_signature:
                        # If we have a native HTML signature, use it.
                        # It's a full fragment, so we just append it.
                        full_html_body = f"{html_body}{html_signature}"
                    elif plain_signature:
                        # If not, convert the plain text signature to HTML as a fallback.
                        html_fallback_sig = f"-- <br>{_markdown_to_html(plain_signature.replace('--', ''))}"
                        full_html_body = f"{html_body}<br><br>{html_fallback_sig}"
                    else:
                        full_html_body = html_body

                    # 5. Create body parts
                    part1 = MIMEText(full_plain_body, "plain")
                    part2 = MIMEText(full_html_body, "html")
                    reply_message.attach(part1)
                    reply_message.attach(part2)

                    # 6. Find drafts folder and save
                    drafts_folder = self._find_drafts_folder(mail)
                    logger.info(f"Saving draft reply to folder: {drafts_folder}")
                    
                    message_string = reply_message.as_string()
                    result = mail.append(drafts_folder, None, None, message_string.encode("utf-8"))

                    if result[0] == "OK":
                        return {"success": True, "message": f"Draft reply saved to {drafts_folder}."}
                    else:
                        error_msg = f"Error creating draft reply: {result[1][0].decode() if result[1] else 'Unknown error'}"
                        logger.error(error_msg)
                        return {"success": False, "message": error_msg}

            except (ValueError, ConnectionError) as e:
                error_msg = f"IMAP connection failed during draft_reply: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return {"success": False, "message": error_msg}
            except Exception as e:
                error_msg = f"Error creating draft reply: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return {"success": False, "message": error_msg}
        
        return await asyncio.get_running_loop().run_in_executor(None, _create_and_save_draft) 
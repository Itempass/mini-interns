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
        pass

    @contextlib.contextmanager
    def _connect(self) -> Generator[imaplib.IMAP4_SSL, None, None]:
        """
        Connects to the IMAP server, logs in, and yields the connection.
        Ensures logout and connection closure.
        """
        settings = load_app_settings()
        if not settings.IMAP_SERVER or not settings.IMAP_USERNAME or not settings.IMAP_PASSWORD:
            logger.error("IMAP settings are not configured. Cannot connect.")
            raise ValueError("IMAP settings (server, username, password) are not fully configured.")
        
        mail = None
        try:
            logger.info(f"Connecting to IMAP server: {settings.IMAP_SERVER}")
            mail = imaplib.IMAP4_SSL(settings.IMAP_SERVER)
            mail.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
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
        # A robust method, mirroring the plain-text approach. We look for the most
        # common set of trailing HTML elements in the message body.
        
        # Use the plain text signature to find "golden" emails that definitely contain a signature.
        golden_emails = []
        for b in email_bodies:
            if b.get('html') and b.get('text'):
                # We check the entire visible text, not just the "reply" part,
                # as the parser can sometimes misclassify signatures.
                email_message = EmailReplyParser.read(b['text'])
                content_with_signature = "\n".join([f.content for f in email_message.fragments if not f.quoted])
                if content_with_signature.strip().endswith(final_plain_signature):
                    golden_emails.append(b)

        logger.info(f"Found {len(golden_emails)} golden emails to check for an HTML signature.")

        if len(golden_emails) < 2:
            return final_plain_signature, None

        parsed_bodies = [BeautifulSoup(email['html'], 'lxml') for email in golden_emails]

        # --- Shortcut: Check for known signature classes ---
        signature_classes = ['gmail_signature']
        for class_name in signature_classes:
            candidate_tags = [soup.find(class_=class_name) for soup in parsed_bodies]
            valid_candidates = [str(tag) for tag in candidate_tags if tag]

            if len(valid_candidates) >= 2:
                most_common_candidate, count = Counter(valid_candidates).most_common(1)[0]
                # If we have a confident match, return it.
                if count >= 2:
                    logger.info(f"Found HTML signature using shortcut class: '{class_name}'")
                    # Clean up the HTML for consistency.
                    soup = BeautifulSoup(most_common_candidate, 'lxml')
                    return final_plain_signature, str(soup.body.contents[0])

        logger.info("Shortcut signature detection did not yield a confident result, proceeding to general logic.")
        # --- End of Shortcut ---

        best_html_signature = None
        last_html_score = -1

        # Check for signatures made of 1 to 5 trailing elements
        for element_count in range(1, 6):
            candidates = []
            for soup in parsed_bodies:
                if not soup.body:
                    continue
                
                # Get direct children of the body tag
                body_children = soup.body.find_all(recursive=False)
                
                if len(body_children) < element_count:
                    continue

                # Take the last `element_count` elements as a candidate
                trailing_elements = body_children[-element_count:]
                
                # Join the string representations of the elements to form the candidate signature
                candidate_str = "".join(str(el) for el in trailing_elements)
                candidates.append(candidate_str)
            
            if not candidates:
                continue

            # Find the most common candidate and its frequency
            most_common_candidate, occurrences = Counter(candidates).most_common(1)[0]
            current_score = occurrences
            
            logger.info(f"HTML Detection: For {element_count} elements, best candidate scored {current_score}.")

            # If the score drops, the previous, shorter signature was the most consistent one.
            if current_score < last_html_score:
                logger.info("Score is lower than the last score. Breaking loop.")
                break

            # If the score is the same or better, we prefer the longer (more specific) signature.
            if current_score >= last_html_score:
                best_html_signature = most_common_candidate
                last_html_score = current_score
            
            # If the signature is not common enough, no need to check for longer versions.
            if current_score < 2:
                logger.info("Score is less than 2. Breaking loop.")
                break

        final_html_signature = None
        if last_html_score >= 2:
            final_html_signature = best_html_signature
            logger.info(f"Final confirmed HTML signature (Score: {last_html_score}): '{final_html_signature[:100]}...'")
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
                    thread_mailbox, thread_uids = threading_service.get_thread_uids(initial_uid, current_mailbox=initial_mailbox)

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

    async def fetch_recent_threads(self, max_emails_to_scan: int = 500) -> List[List[RawEmail]]:
        """
        Efficiently fetches recent unique threads from the sent folder within a single connection.
        This method correctly handles threads that span multiple mailboxes by grouping fetches.
        """
        def _fetch_threads_optimized() -> List[List[RawEmail]]:
            try:
                with self._connect() as mail:
                    # 1. Start in the 'Sent' folder to find recent conversations
                    sent_folder = self._find_sent_folder(mail)
                    try:
                        mail.select(f'"{sent_folder}"', readonly=True)
                    except imaplib.IMAP4.error:
                        logger.error(f"Could not select sent folder '{sent_folder}'.")
                        return []

                    typ, data = mail.uid('search', None, 'ALL')
                    if typ != 'OK' or not data or not data[0]:
                        return []
                    
                    email_uids_bytes = data[0].split()
                    latest_email_uids_bytes = email_uids_bytes[-max_emails_to_scan:]

                    # 2. Discover all unique threads, returning the mailbox and UIDs for each.
                    #    This must be done from a selected mailbox, so we stay in 'sent_folder' for discovery.
                    threading_service = ThreadingService(mail)
                    processed_thread_identifiers = set() 
                    threads_to_fetch = [] # List of (mailbox, uids_list)
                    logger.info(f"Starting thread discovery from initial folder: {sent_folder}")

                    for uid_bytes in reversed(latest_email_uids_bytes):
                        uid_str = uid_bytes.decode()
                        
                        if uid_str in processed_thread_identifiers:
                            continue

                        logger.info(f"[{sent_folder}] Handing off UID {uid_str} to ThreadingService.")
                        thread_mailbox, thread_uids = threading_service.get_thread_uids(uid_str, current_mailbox=sent_folder)
                        if thread_uids:
                            # A thread is uniquely identified by its list of UIDs
                            thread_identifier = tuple(sorted(thread_uids))
                            if thread_identifier not in processed_thread_identifiers:
                                threads_to_fetch.append((thread_mailbox, thread_uids))
                                processed_thread_identifiers.add(thread_identifier)
                                processed_thread_identifiers.add(uid_str) # Add starting UID too

                    # 3. Group the threads by their mailbox to minimize SELECT commands
                    threads_by_mailbox = {}
                    for mailbox, uids in threads_to_fetch:
                        if mailbox not in threads_by_mailbox:
                            threads_by_mailbox[mailbox] = []
                        threads_by_mailbox[mailbox].append(uids)

                    # 4. Fetch all messages, selecting each mailbox only once
                    all_threads = []
                    for mailbox, list_of_thread_uids in threads_by_mailbox.items():
                        try:
                            mail.select(f'"{mailbox}"', readonly=True)
                            logger.info(f"Switched to mailbox '{mailbox}' to fetch {len(list_of_thread_uids)} threads.")
                        except imaplib.IMAP4.error:
                            logger.error(f"Failed to select mailbox '{mailbox}'. Skipping threads.")
                            continue

                        for thread_uids in list_of_thread_uids:
                            current_thread_emails = []
                            for uid in thread_uids:
                                raw_msg = self._fetch_raw_message_from_selected_mailbox(mail, uid, mailbox)
                                if raw_msg:
                                    current_thread_emails.append(raw_msg)
                            
                            if current_thread_emails:
                                all_threads.append(current_thread_emails)
                    
                    return all_threads

            except (ValueError, ConnectionError) as e:
                logger.error(f"IMAP connection failed during fetch_recent_threads: {e}")
                return []
            except imaplib.IMAP4.error as e:
                logger.error(f"Error fetching recent threads: {e}", exc_info=True)
                return []

        return await asyncio.get_running_loop().run_in_executor(None, _fetch_threads_optimized)

    def _fetch_raw_message_from_selected_mailbox(self, mail: imaplib.IMAP4_SSL, uid: str, mailbox: str) -> Optional[RawEmail]:
        """
        Fetches a single raw email message from the already selected mailbox.
        Helper for bulk operations.
        """
        typ, data = mail.uid('fetch', uid.encode(), '(RFC822)')
        if typ == 'OK' and data and data[0] is not None:
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    contextual_id = create_contextual_id(mailbox, uid)
                    return RawEmail(uid=contextual_id, msg=msg)
        logger.warning(f"Failed to fetch raw message for UID {uid} from selected mailbox {mailbox}")
        return None

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
                    # Load fresh settings for this operation
                    settings = load_app_settings()
                    
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
                    reply_message["From"] = settings.IMAP_USERNAME
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
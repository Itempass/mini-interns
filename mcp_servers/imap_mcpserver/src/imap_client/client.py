from __future__ import annotations
import imaplib
import email
import os
import re
import base64
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from email_reply_parser import EmailReplyParser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header
import email.utils
try:
    import html2text
except ImportError:
    html2text = None

from .models import EmailMessage, EmailThread
from .bulk_threading import fetch_recent_threads_bulk
from .helpers.contextual_id import create_contextual_id

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# IMAP connection details
IMAP_SERVER = "imap.gmail.com"
IMAP_USERNAME = os.getenv("IMAP_USERNAME", "arthur@itempass.com")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")
IMAP_PORT = 993

def _extract_reply_from_gmail_html(html_body: str) -> str:
    """Extract only the reply portion from Gmail HTML, removing quoted content"""
    try:
        # Gmail patterns to identify quoted content
        quote_patterns = [
            r'<div class="gmail_quote[^"]*">.*?</div>',  # Gmail quote container
            r'<blockquote[^>]*class="[^"]*gmail_quote[^"]*"[^>]*>.*?</blockquote>',  # Gmail blockquote
            r'<div[^>]*class="[^"]*gmail_attr[^"]*"[^>]*>.*?</div>',  # Gmail attribution
        ]
        
        # Remove quoted sections
        cleaned_html = html_body
        for pattern in quote_patterns:
            cleaned_html = re.sub(pattern, '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
        
        # Also remove common quote patterns that might not have Gmail classes
        other_patterns = [
            r'<br><br><div class="gmail_quote">.*',  # Everything after gmail_quote start
            r'<div class="gmail_quote.*',  # Everything from gmail_quote start
        ]
        
        for pattern in other_patterns:
            cleaned_html = re.sub(pattern, '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
        
        return cleaned_html.strip()
        
    except Exception as e:
        logger.warning(f"Error extracting reply from Gmail HTML: {e}")
        return html_body

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
                text_body = part.get_payload(decode=True).decode(charset, errors='ignore')
            elif content_type == "text/html" and not html_body:
                html_body = part.get_payload(decode=True).decode(charset, errors='ignore')
    else:
        charset = msg.get_content_charset() or 'utf-8'
        content = msg.get_payload(decode=True)
        if isinstance(content, bytes):
            content = content.decode(charset, errors='ignore')
        
        if msg.get_content_type() == "text/html":
            html_body = content
        else:
            text_body = content
    
    # Use EmailReplyParser FIRST on plain text to extract only the reply
    reply_text = ""
    if text_body:
        try:
            reply_text = EmailReplyParser.parse_reply(text_body)
        except Exception as e:
            logger.warning(f"Error parsing email reply: {e}")
            reply_text = text_body
    
    # Determine the raw body (prefer HTML if available, otherwise plain text)
    # For HTML, extract only the reply portion
    if html_body:
        raw_body = _extract_reply_from_gmail_html(html_body)
    else:
        raw_body = reply_text if reply_text else text_body
    
    # Convert HTML to markdown if we have HTML
    markdown_body = ""
    if html_body and html2text:
        try:
            # Extract only the reply part from Gmail HTML before converting to markdown
            reply_html = _extract_reply_from_gmail_html(html_body)
            
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.body_width = 0  # Don't wrap lines
            markdown_body = h.handle(reply_html).strip()
        except Exception as e:
            logger.warning(f"Error converting HTML to markdown: {e}")
            markdown_body = text_body if text_body else html_body
    else:
        # No HTML or no html2text library, use plain text
        markdown_body = text_body if text_body else html_body
    
    # Create cleaned version (remove markdown formatting from reply)
    cleaned_body = ""
    if reply_text:
        cleaned_body = reply_text
        # Remove markdown links [text](url) -> text
        cleaned_body = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', cleaned_body)
        # Remove bold/italic formatting **text** -> text, *text* -> text
        cleaned_body = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned_body)
        cleaned_body = re.sub(r'\*([^*]+)\*', r'\1', cleaned_body)
        # Remove other markdown formatting
        cleaned_body = re.sub(r'`([^`]+)`', r'\1', cleaned_body)  # Remove code formatting
        cleaned_body = re.sub(r'#+\s*', '', cleaned_body)  # Remove headers
        # Clean up: remove extra line breaks, normalize whitespace
        cleaned_body = re.sub(r'\n\s*\n', ' ', cleaned_body)  # Replace multiple newlines with space
        cleaned_body = re.sub(r'\s+', ' ', cleaned_body)  # Normalize whitespace
        cleaned_body = cleaned_body.strip()
    
    return {
        'raw': raw_body or "",
        'markdown': markdown_body or "",
        'cleaned': cleaned_body or ""
    }

def _find_uid_by_message_id(mail: imaplib.IMAP4_SSL, message_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Find UID and mailbox for a given Message-ID header."""
    mailboxes_to_search = ["INBOX", "[Gmail]/All Mail", "[Gmail]/Sent Mail"]
    
    for mailbox in mailboxes_to_search:
        try:
            mail.select(f'"{mailbox}"', readonly=True)
            typ, data = mail.uid('search', None, f'(HEADER Message-ID "{message_id}")')
            
            if typ == 'OK' and data and data[0]:
                uids = data[0].split()
                if uids:
                    uid = uids[0].decode()
                    return uid, mailbox
        except Exception as e:
            logger.warning(f"Error searching {mailbox}: {e}")
            continue
    
    return None, None

def _get_message_by_id_sync(message_id: str) -> Optional[EmailMessage]:
    """
    Synchronous function to get a single EmailMessage by its Message-ID.
    Searches across INBOX and [Gmail]/All Mail to find the message.
    """
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_USERNAME, IMAP_PASSWORD)
        
        try:
            # Search in INBOX first
            mail.select('INBOX', readonly=True)
            typ, data = mail.uid('search', None, f'(HEADER Message-ID "{message_id}")')
            
            if typ == 'OK' and data[0]:
                uid = data[0].split()[0].decode()
                return _fetch_single_message(mail, uid, 'INBOX')
            
            # If not found in INBOX, search in [Gmail]/All Mail
            mail.select('"[Gmail]/All Mail"', readonly=True)
            typ, data = mail.uid('search', None, f'(HEADER Message-ID "{message_id}")')
            
            if typ == 'OK' and data[0]:
                uid = data[0].split()[0].decode()
                return _fetch_single_message(mail, uid, '[Gmail]/All Mail')
            
            return None
            
        finally:
            mail.close()
            mail.logout()
        
    except Exception as e:
        logger.error(f"Error getting message by ID {message_id}: {e}")
        return None

def _fetch_single_message(mail: imaplib.IMAP4_SSL, uid: str, folder: str) -> Optional[EmailMessage]:
    """Helper function to fetch a single message with labels"""
    try:
        typ, data = mail.uid('fetch', uid, '(RFC822 X-GM-LABELS)')
        if typ != 'OK' or not data or not isinstance(data[0], tuple):
            return None
        
        header_info = data[0][0].decode() if isinstance(data[0][0], bytes) else str(data[0][0])
        msg = email.message_from_bytes(data[0][1])
        message_id_header = msg.get('Message-ID', '').strip('<>')
        
        # Skip if no Message-ID
        if not message_id_header:
            return None
        
        # Create contextual ID
        contextual_id = create_contextual_id(folder, uid)
        
        # Extract Gmail labels from header info
        labels = []
        labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
        if labels_match:
            labels_str = labels_match.group(1)
            labels = re.findall(r'"([^"]*)"', labels_str)
            labels = [label.replace('\\\\', '\\') for label in labels]
        
        # Extract body in multiple formats
        body_formats = _extract_body_formats(msg)
        
        return EmailMessage(
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
        )
        
    except Exception as e:
        logger.error(f"Error fetching single message {uid} from {folder}: {e}")
        return None

def _get_complete_thread_sync(message_id: str) -> Optional[EmailThread]:
    """Synchronous function to get complete thread"""
    try:
        # Connect to Gmail
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_USERNAME, IMAP_PASSWORD)
        
        try:
            # Step 1: Find the message and get its thread ID
            uid, mailbox = _find_uid_by_message_id(mail, message_id)
            if not uid:
                return None
            
            # Step 2: Get X-GM-THRID from the message
            mail.select(f'"{mailbox}"', readonly=True)
            typ, data = mail.uid('fetch', uid, '(X-GM-THRID)')
            if typ != 'OK' or not data:
                return None
            
            thrid_match = re.search(rb'X-GM-THRID (\d+)', data[0])
            if not thrid_match:
                return None
            
            gmail_thread_id = thrid_match.group(1).decode()
            
            # Step 3: Search for all thread messages in All Mail
            mail.select('"[Gmail]/All Mail"', readonly=True)
            typ, data = mail.uid('search', None, f'(X-GM-THRID {gmail_thread_id})')
            if typ != 'OK' or not data:
                return None
            
            thread_uids = [uid.decode() for uid in data[0].split()]
            
            # Step 4: Fetch all messages with labels in one call
            uid_list = ','.join(thread_uids)
            typ, data = mail.uid('fetch', uid_list, '(RFC822 X-GM-LABELS)')
            if typ != 'OK' or not data:
                return None
            
            # Step 5: Parse messages and labels
            messages = []
            i = 0
            while i < len(data):
                if isinstance(data[i], tuple) and len(data[i]) >= 2:
                    header_info = data[i][0].decode() if isinstance(data[i][0], bytes) else str(data[i][0])
                    msg = email.message_from_bytes(data[i][1])
                    message_id_header = msg.get('Message-ID', '').strip('<>')
                    
                    # Skip draft messages (no Message-ID)
                    if not message_id_header:
                        i += 1
                        continue
                    
                    # Extract UID from header info
                    uid_match = re.search(r'(\d+) \(', header_info)
                    uid = uid_match.group(1) if uid_match else thread_uids[len(messages)]
                    
                    # Create contextual ID
                    contextual_id = create_contextual_id('[Gmail]/All Mail', uid)
                    
                    # Extract Gmail labels from header info
                    labels = []
                    labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
                    if labels_match:
                        labels_str = labels_match.group(1)
                        labels = re.findall(r'"([^"]*)"', labels_str)
                        labels = [label.replace('\\\\', '\\') for label in labels]
                    
                    # Extract body in multiple formats
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
                i += 1
            
            # Step 6: Create EmailThread from messages
            if messages:
                return EmailThread.from_messages(messages, gmail_thread_id)
            
            return None
            
        finally:
            mail.close()
            mail.logout()
            
    except Exception as e:
        logger.error(f"Error getting thread: {e}")
        return None

def _get_recent_message_ids_sync(count: int = 20) -> List[str]:
    """Synchronous function to get recent Message-IDs from INBOX"""
    try:
        # Connect to Gmail
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_USERNAME, IMAP_PASSWORD)
        
        try:
            mail.select('"INBOX"', readonly=True)
            typ, data = mail.uid('search', None, 'ALL')
            
            if typ != 'OK' or not data:
                return []
            
            # Get recent UIDs
            all_uids = data[0].split()
            recent_uids = all_uids[-count:] if len(all_uids) >= count else all_uids
            
            # Fetch Message-IDs for these UIDs
            message_ids = []
            for uid in recent_uids:
                typ, data = mail.uid('fetch', uid, '(BODY[HEADER.FIELDS (MESSAGE-ID)])')
                if typ == 'OK' and data and data[0]:
                    for response_part in data:
                        if isinstance(response_part, tuple):
                            headers = response_part[1].decode()
                            message_id_match = re.search(r'Message-ID:\s*<([^>]+)>', headers, re.IGNORECASE)
                            if message_id_match:
                                message_ids.append(message_id_match.group(1))
                            break
            
            return message_ids
            
        finally:
            mail.close()
            mail.logout()
            
    except Exception as e:
        logger.error(f"Error getting inbox message IDs: {e}")
        return []

def _get_recent_messages_from_folder_sync(folder: str, count: int = 20) -> List[EmailMessage]:
    """Synchronous function to get recent messages from a specific folder"""
    try:
        # Connect to Gmail
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_USERNAME, IMAP_PASSWORD)
        
        try:
            mail.select(f'"{folder}"', readonly=True)
            typ, data = mail.uid('search', None, 'ALL')
            
            if typ != 'OK' or not data:
                return []
            
            # Get recent UIDs
            all_uids = data[0].split()
            recent_uids = all_uids[-count:] if len(all_uids) >= count else all_uids
            
            # Fetch all messages with labels in one call
            uid_list = ','.join([uid.decode() for uid in recent_uids])
            typ, data = mail.uid('fetch', uid_list, '(RFC822 X-GM-LABELS)')
            if typ != 'OK' or not data:
                return []
            
            # Parse messages
            messages = []
            i = 0
            while i < len(data):
                if isinstance(data[i], tuple) and len(data[i]) >= 2:
                    header_info = data[i][0].decode() if isinstance(data[i][0], bytes) else str(data[i][0])
                    msg = email.message_from_bytes(data[i][1])
                    message_id_header = msg.get('Message-ID', '').strip('<>')
                    
                    # Skip draft messages (no Message-ID)
                    if not message_id_header:
                        i += 1
                        continue
                    
                    # Extract UID from header info
                    uid_match = re.search(r'(\d+) \(', header_info)
                    uid = uid_match.group(1) if uid_match else recent_uids[len(messages)].decode()
                    
                    # Create contextual ID
                    contextual_id = create_contextual_id(folder, uid)
                    
                    # Extract Gmail labels from header info
                    labels = []
                    labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
                    if labels_match:
                        labels_str = labels_match.group(1)
                        labels = re.findall(r'"([^"]*)"', labels_str)
                        labels = [label.replace('\\\\', '\\') for label in labels]
                    
                    # Extract body in multiple formats
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
                i += 1
            
            return messages
            
        finally:
            mail.close()
            mail.logout()
            
    except Exception as e:
        logger.error(f"Error getting messages from {folder}: {e}")
        return []

def _markdown_to_html(markdown_text: str) -> str:
    """Convert simple markdown formatting to HTML"""
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

def _find_drafts_folder(mail: imaplib.IMAP4_SSL) -> str:
    """Find the correct drafts folder name by trying common variations"""
    draft_folders = ["[Gmail]/Drafts", "DRAFTS", "Drafts", "[Google Mail]/Drafts"]
    
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
                    logger.info(f"Found drafts folder: {draft_folder}")
                    return draft_folder
            # Search for any folder containing "draft"
            for folder_name in folder_list:
                if "draft" in folder_name.lower():
                    logger.info(f"Found drafts folder by search: {folder_name}")
                    return folder_name
    except Exception as e:
        logger.warning(f"Error listing folders: {e}")
    
    # Default fallback
    logger.info("Using default drafts folder: [Gmail]/Drafts")
    return "[Gmail]/Drafts"

def _get_user_signature() -> Tuple[Optional[str], Optional[str]]:
    """Get user signature from recent sent emails (simplified version)"""
    # For now, return None - we can implement signature detection later
    # This is a simplified version to get the basic functionality working
    return None, None

def _draft_reply_sync(original_message: EmailMessage, reply_body: str) -> Dict[str, Any]:
    """Synchronous function to create a draft reply"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_USERNAME, IMAP_PASSWORD)
        
        try:
            # Prepare reply headers
            original_subject = original_message.subject
            reply_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
            
            # Use Reply-To header if available, otherwise From
            reply_to_email = original_message.from_
            to_email = email.utils.parseaddr(reply_to_email)[1]
            
            # Create the reply message
            reply_message = MIMEMultipart("alternative")
            reply_message["Subject"] = reply_subject
            reply_message["From"] = IMAP_USERNAME
            reply_message["To"] = to_email
            
            # Handle CC
            if original_message.cc:
                # Parse CC addresses
                cc_emails = [
                    email_address for _, email_address 
                    in email.utils.getaddresses([original_message.cc]) 
                    if email_address
                ]
                if cc_emails:
                    reply_message['Cc'] = ', '.join(cc_emails)
            
            # Add threading headers
            if original_message.message_id:
                reply_message["In-Reply-To"] = f"<{original_message.message_id}>"
                reply_message["References"] = f"<{original_message.message_id}>"
            
            reply_message["Date"] = email.utils.formatdate(localtime=True)
            
            # Get signature (simplified for now)
            plain_signature, html_signature = _get_user_signature()
            
            # Prepare plain part
            full_plain_body = reply_body
            if plain_signature:
                full_plain_body = f"{reply_body}\n\n{plain_signature}"
            
            # Prepare HTML part
            html_body = _markdown_to_html(reply_body)
            if html_signature:
                full_html_body = f"{html_body}{html_signature}"
            elif plain_signature:
                html_fallback_sig = f"-- <br>{_markdown_to_html(plain_signature.replace('--', ''))}"
                full_html_body = f"{html_body}<br><br>{html_fallback_sig}"
            else:
                full_html_body = html_body
            
            # Create body parts
            part1 = MIMEText(full_plain_body, "plain")
            part2 = MIMEText(full_html_body, "html")
            reply_message.attach(part1)
            reply_message.attach(part2)
            
            # Find drafts folder and save
            drafts_folder = _find_drafts_folder(mail)
            logger.info(f"Saving draft reply to folder: {drafts_folder}")
            
            message_string = reply_message.as_string()
            result = mail.append(drafts_folder, None, None, message_string.encode("utf-8"))
            
            if result[0] == "OK":
                return {"success": True, "message": f"Draft reply saved to {drafts_folder}."}
            else:
                error_msg = f"Error creating draft reply: {result[1][0].decode() if result[1] else 'Unknown error'}"
                logger.error(error_msg)
                return {"success": False, "message": error_msg}
                
        finally:
            try:
                mail.logout()
            except Exception as e:
                logger.warning(f"Error during logout: {e}")
            
    except Exception as e:
        error_msg = f"Error creating draft reply: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"success": False, "message": error_msg}

# --- Public API Functions ---

async def get_recent_inbox_message_ids(count: int = 20) -> List[str]:
    """
    Get recent Message-IDs from INBOX.
    """
    return await asyncio.get_event_loop().run_in_executor(None, _get_recent_message_ids_sync, count)

async def get_message_by_id(message_id: str) -> Optional[EmailMessage]:
    """
    Get a single EmailMessage by its Message-ID.
    Searches across all folders to find the message.
    """
    return await asyncio.get_event_loop().run_in_executor(None, _get_message_by_id_sync, message_id)

async def get_complete_thread(message: EmailMessage) -> Optional[EmailThread]:
    """
    Get complete thread with folder information for a given EmailMessage.
    Returns an EmailThread with all messages and their Gmail labels.
    """
    return await asyncio.get_event_loop().run_in_executor(None, _get_complete_thread_sync, message.message_id)

async def get_recent_inbox_messages(count: int = 20) -> List[EmailMessage]:
    """
    Get recent messages from INBOX.
    Returns a list of EmailMessage objects.
    """
    return await asyncio.get_event_loop().run_in_executor(None, _get_recent_messages_from_folder_sync, "INBOX", count)

async def get_recent_sent_messages(count: int = 20) -> List[EmailMessage]:
    """
    Get recent messages from Sent folder.
    Returns a list of EmailMessage objects.
    """
    return await asyncio.get_event_loop().run_in_executor(None, _get_recent_messages_from_folder_sync, "[Gmail]/Sent Mail", count)

async def draft_reply(original_message: EmailMessage, reply_body: str) -> Dict[str, Any]:
    """
    Create a draft reply to the given original EmailMessage.
    
    Args:
        original_message: The EmailMessage we are replying to
        reply_body: Reply body content in markdown format
        
    Returns:
        Dict with 'success' boolean and 'message' string
    """
    return await asyncio.get_event_loop().run_in_executor(None, _draft_reply_sync, original_message, reply_body)

async def get_recent_threads_bulk(target_thread_count: int = 50, max_age_months: int = 6) -> Tuple[List[EmailThread], Dict[str, float]]:
    """
    Fetch a target number of recent email threads efficiently using bulk operations.
    
    This is the high-performance version of thread fetching that:
    - Dynamically scans until target_thread_count unique threads are found
    - Uses batch X-GM-THRID fetches to minimize IMAP round trips
    - Respects max_age_months limit (default 6 months)
    - Provides smart deduplication to avoid processing duplicate threads
    - Uses a single persistent IMAP connection for optimal performance
    
    Args:
        target_thread_count: Number of unique threads to return (default 50)
        max_age_months: Maximum age of threads to consider in months (default 6)
        
    Returns:
        Tuple of (threads_list, timing_dict) where:
        - threads_list: List of EmailThread objects
        - timing_dict: Dictionary with timing breakdown and performance metrics
        
    Example:
        # Get 25 recent threads
        threads, timing = await get_recent_threads_bulk(target_thread_count=25)
        print(f"Found {len(threads)} threads in {timing['total_time']:.2f}s")
        
        # Get 10 threads from last 3 months
        threads, timing = await get_recent_threads_bulk(target_thread_count=10, max_age_months=3)
    """
    return await fetch_recent_threads_bulk(
        target_thread_count=target_thread_count,
        max_age_months=max_age_months,
        imap_server=IMAP_SERVER,
        imap_username=IMAP_USERNAME,
        imap_password=IMAP_PASSWORD,
        imap_port=IMAP_PORT
    ) 
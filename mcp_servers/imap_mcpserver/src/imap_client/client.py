from __future__ import annotations
import imaplib
import email
import os
import re
import base64
import asyncio
import logging
from typing import List, Optional, Tuple, Dict
from dotenv import load_dotenv
from email_reply_parser import EmailReplyParser
try:
    import html2text
except ImportError:
    html2text = None

from .models import EmailMessage, EmailThread

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# IMAP connection details
IMAP_SERVER = "imap.gmail.com"
IMAP_USERNAME = os.getenv("IMAP_USERNAME", "arthur@itempass.com")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")
IMAP_PORT = 993

def _create_contextual_id(mailbox: str, uid: str) -> str:
    """Creates a contextual ID from a mailbox and a UID."""
    encoded_mailbox = base64.b64encode(mailbox.encode('utf-8')).decode('utf-8')
    return f"{encoded_mailbox}:{uid}"

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
    
    # Determine the raw body (prefer HTML if available, otherwise plain text)
    # For HTML, extract only the reply portion
    if html_body:
        raw_body = _extract_reply_from_gmail_html(html_body)
    else:
        raw_body = reply_text if reply_text else text_body
    
    # Use EmailReplyParser FIRST on plain text to extract only the reply
    reply_text = ""
    if text_body:
        try:
            reply_text = EmailReplyParser.parse_reply(text_body)
        except Exception as e:
            logger.warning(f"Error parsing email reply: {e}")
            reply_text = text_body
    
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
                    contextual_id = _create_contextual_id('[Gmail]/All Mail', uid)
                    
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

# --- Public API Functions ---

async def get_recent_inbox_message_ids(count: int = 20) -> List[str]:
    """
    Get recent Message-IDs from INBOX.
    """
    return await asyncio.get_event_loop().run_in_executor(None, _get_recent_message_ids_sync, count)

async def get_complete_thread(message_id: str) -> Optional[EmailThread]:
    """
    Get complete thread with folder information for a given Message-ID.
    Returns an EmailThread with all messages and their Gmail labels.
    """
    return await asyncio.get_event_loop().run_in_executor(None, _get_complete_thread_sync, message_id) 
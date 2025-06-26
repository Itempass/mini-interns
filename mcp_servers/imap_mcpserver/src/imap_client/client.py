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

from mcp_servers.imap_mcpserver.src.imap_client.models import EmailMessage, EmailThread
from mcp_servers.imap_mcpserver.src.imap_client.internals.bulk_threading import fetch_recent_threads_bulk
from mcp_servers.imap_mcpserver.src.imap_client.helpers.contextual_id import create_contextual_id
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import imap_connection, IMAPConnectionError
from mcp_servers.imap_mcpserver.src.imap_client.helpers.body_parser import extract_body_formats

load_dotenv(override=True)

logger = logging.getLogger(__name__)

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
        with imap_connection() as mail:
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
        body_formats = extract_body_formats(msg)
        
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
        with imap_connection() as mail:
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
                i += 1
            
            # Step 6: Create EmailThread from messages
            if messages:
                return EmailThread.from_messages(messages, gmail_thread_id)
            
            return None
            
    except Exception as e:
        logger.error(f"Error getting thread: {e}")
        return None

def _get_recent_message_ids_sync(count: int = 20) -> List[str]:
    """Synchronous function to get recent Message-IDs from INBOX"""
    try:
        with imap_connection() as mail:
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
            
    except Exception as e:
        logger.error(f"Error getting inbox message IDs: {e}")
        return []

def _get_recent_messages_from_folder_sync(folder: str, count: int = 20) -> List[EmailMessage]:
    """Synchronous function to get recent messages from a specific folder"""
    try:
        with imap_connection() as mail:
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
                i += 1
            
            return messages
            
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
    """Get user signature from recent sent emails using Gmail signature shortcut"""
    try:
        with imap_connection() as mail:
            # Select Gmail sent folder
            mail.select('"[Gmail]/Sent Mail"', readonly=True)
            typ, data = mail.uid('search', None, 'ALL')
            
            if typ != 'OK' or not data or not data[0]:
                logger.info("No emails found in sent folder.")
                return None, None
            
            email_uids = data[0].split()
            if not email_uids:
                return None, None
            
            # Get last 5 sent emails (smaller sample for Gmail shortcut)
            latest_email_uids = email_uids[-10:]
            logger.info(f"Analyzing last {len(latest_email_uids)} sent emails for Gmail signature.")
            
            html_bodies = []
            plain_bodies = []
            
            for uid in latest_email_uids:
                typ, data = mail.uid('fetch', uid, '(RFC822)')
                if typ != 'OK':
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
                        
                        if html_body:
                            html_bodies.append(html_body)
                        if plain_body:
                            plain_bodies.append(plain_body)
            
            if len(html_bodies) < 2:
                logger.info("Not enough HTML emails to detect Gmail signature.")
                return None, None
            
            # Gmail signature shortcut - look for gmail_signature class
            try:
                from bs4 import BeautifulSoup
                from collections import Counter
                
                parsed_bodies = [BeautifulSoup(html, 'lxml') for html in html_bodies]
                
                # Look for Gmail signature class
                signature_candidates = []
                for soup in parsed_bodies:
                    gmail_sig = soup.find(class_='gmail_signature')
                    if gmail_sig:
                        signature_candidates.append(str(gmail_sig))
                
                if len(signature_candidates) >= 2:
                    # Find most common signature
                    most_common_sig, count = Counter(signature_candidates).most_common(1)[0]
                    if count >= 2:
                        logger.info(f"Found Gmail signature in {count} emails using gmail_signature class")
                        
                        # Extract plain text version from the same emails
                        plain_signature = None
                        if plain_bodies:
                            # Simple approach: look for common trailing lines in plain text
                            from email_reply_parser import EmailReplyParser
                            plain_replies = []
                            for plain_body in plain_bodies:
                                try:
                                    reply = EmailReplyParser.parse_reply(plain_body)
                                    if reply != plain_body:  # If parsing removed something, it was likely a signature
                                        # Get the removed part as potential signature
                                        signature_part = plain_body.replace(reply, '').strip()
                                        if signature_part:
                                            plain_replies.append(signature_part)
                                except:
                                    pass
                            
                            if plain_replies and len(plain_replies) >= 2:
                                most_common_plain, plain_count = Counter(plain_replies).most_common(1)[0]
                                if plain_count >= 2:
                                    plain_signature = most_common_plain.strip()
                        
                        return plain_signature, most_common_sig
                
                logger.info("Gmail signature shortcut did not find consistent signatures.")
                return None, None
                
            except ImportError:
                logger.warning("BeautifulSoup not available for HTML signature detection")
                return None, None
            
    except IMAPConnectionError as e:
        logger.error(f"IMAP connection error getting Gmail signature: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error getting Gmail signature: {e}")
        return None, None

def _draft_reply_sync(original_message: EmailMessage, reply_body: str) -> Dict[str, Any]:
    """Synchronous function to create a draft reply"""
    try:
        with imap_connection() as mail:
            # Prepare reply headers
            original_subject = original_message.subject
            reply_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
            
            # Use Reply-To header if available, otherwise From
            reply_to_email = original_message.from_
            to_email = email.utils.parseaddr(reply_to_email)[1]
            
            # Create the reply message
            reply_message = MIMEMultipart("alternative")
            reply_message["Subject"] = reply_subject
            reply_message["From"] = os.getenv("IMAP_USERNAME")
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

async def get_message_by_id(message_id: str, mailbox: str = "INBOX") -> Optional[EmailMessage]:
    """
    Get a single EmailMessage by its Message-ID.
    Searches across all folders to find the message.
    """
    return await asyncio.get_event_loop().run_in_executor(None, _get_message_by_id_sync, message_id)

async def get_complete_thread(source_message: EmailMessage) -> Optional[EmailThread]:
    """
    Get complete thread with folder information for a given EmailMessage.
    Returns an EmailThread with all messages and their Gmail labels.
    """
    return await asyncio.get_event_loop().run_in_executor(None, _get_complete_thread_sync, source_message.message_id)

async def get_recent_inbox_messages(count: int = 10) -> List[EmailMessage]:
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
    """Create a draft reply for a given message."""
    return await asyncio.to_thread(_draft_reply_sync, original_message, reply_body)

async def get_recent_threads_bulk(target_thread_count: int = 50, max_age_months: int = 6) -> Tuple[List[EmailThread], Dict[str, float]]:
    """
    High-performance bulk retrieval of recent email threads.
    
    This is a pass-through to the optimized bulk fetching implementation,
    which uses a single persistent connection and advanced IMAP features
    to discover and fetch threads efficiently.
    """
    return await fetch_recent_threads_bulk(
        target_thread_count=target_thread_count,
        max_age_months=max_age_months
    ) 
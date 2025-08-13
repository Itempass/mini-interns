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
from email.utils import parseaddr
try:
    import html2text
except ImportError:
    html2text = None

from mcp_servers.imap_mcpserver.src.imap_client.models import EmailMessage, EmailThread
from mcp_servers.imap_mcpserver.src.imap_client.internals.bulk_threading import fetch_recent_threads_bulk
from mcp_servers.imap_mcpserver.src.imap_client.helpers.contextual_id import create_contextual_id
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import imap_connection, IMAPConnectionError, FolderResolver, FolderNotFoundError, acquire_imap_slot
from mcp_servers.imap_mcpserver.src.imap_client.helpers.body_parser import extract_body_formats
from uuid import UUID
from typing import Callable, DefaultDict, Set
from collections import defaultdict

from shared.app_settings import AppSettings, load_app_settings

load_dotenv(override=True)

logger = logging.getLogger(__name__)

def _find_uid_by_message_id(mail: imaplib.IMAP4_SSL, resolver: FolderResolver, message_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Find UID and mailbox for a given Message-ID header."""
    # Use resolver to get key mailboxes. This will raise FolderNotFoundError if a folder is missing.
    mailboxes_to_search = [
        resolver.get_folder_by_attribute('\\Inbox'),
        resolver.get_folder_by_attribute('\\All'),
        resolver.get_folder_by_attribute('\\Sent')
    ]
    
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

def _get_message_by_id_sync(message_id: str, app_settings: AppSettings) -> Optional[EmailMessage]:
    """
    Synchronous function to get a single EmailMessage by its Message-ID.
    Searches across key mailboxes to find the message.
    """
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            # Define search order. This will raise FolderNotFoundError if a folder is missing.
            folders_to_search = [
                resolver.get_folder_by_attribute('\\Inbox'),
                resolver.get_folder_by_attribute('\\All')
            ]

            for folder in folders_to_search:
                try:
                    mail.select(f'"{folder}"', readonly=True)
                    typ, data = mail.uid('search', None, f'(HEADER Message-ID "{message_id}")')
                    
                    if typ == 'OK' and data[0]:
                        uid = data[0].split()[0].decode()
                        return _fetch_single_message(mail, uid, folder)
                except Exception as e:
                    logger.warning(f"Could not search in folder '{folder}': {e}")
                    continue
            
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
        
        # Determine message type based on the presence of the \Sent label
        message_type = 'sent' if '\\Sent' in labels else 'received'
        
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
            in_reply_to=msg.get('In-Reply-To', '').strip('<>'),
            type=message_type
        )
        
    except Exception as e:
        logger.error(f"Error fetching single message {uid} from {folder}: {e}")
        return None

def _get_complete_thread_sync(message_id: str, app_settings: AppSettings) -> Optional[EmailThread]:
    """Synchronous function to get complete thread. It filters out draft messages. """
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            # Step 1: Find the message and get its thread ID
            uid, mailbox = _find_uid_by_message_id(mail, resolver, message_id)
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
            all_mail_folder = resolver.get_folder_by_attribute('\\All')
            mail.select(f'"{all_mail_folder}"', readonly=True)
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
                    
                    # Extract Gmail labels from header info
                    labels = []
                    labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
                    if labels_match:
                        labels_str = labels_match.group(1)
                        # This regex handles both quoted labels (possibly with spaces)
                        # and unquoted labels. It returns a list of tuples, where one
                        # element is the matched label and the other is empty.
                        matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|(\S+)', labels_str)
                        # We flatten the list of tuples into a clean list of strings.
                        raw_labels = [group1 or group2 for group1, group2 in matches]
                        labels = [label.replace('\\\\', '\\') for label in raw_labels]

                    # Skip draft messages (no Message-ID or has \Draft label)
                    if not message_id_header or '\\Draft' in labels:
                        i += 1
                        continue
                    
                    # Determine message type based on the presence of the \Sent label
                    message_type = 'sent' if '\\Sent' in labels else 'received'
                    
                    # Extract UID from header info
                    uid_match = re.search(r'(\d+) \(', header_info)
                    uid = uid_match.group(1) if uid_match else thread_uids[len(messages)]
                    
                    # Create contextual ID
                    contextual_id = create_contextual_id(all_mail_folder, uid)
                    
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
                        in_reply_to=msg.get('In-Reply-To', '').strip('<>'),
                        type=message_type
                    ))
                i += 1
            
            # Step 6: Create EmailThread from messages
            if messages:
                thread = EmailThread.from_messages(messages, gmail_thread_id)

                # Step 7: Get all user-defined labels from the entire thread
                all_special_use_attributes = list(resolver.SPECIAL_USE_ATTRIBUTES) + list(resolver.FALLBACK_MAP.keys())
                
                resolved_special_folders = set()
                for attr in all_special_use_attributes:
                    try:
                        resolved_special_folders.add(attr)
                        resolved_special_folders.add(resolver.get_folder_by_attribute(attr))
                    except FolderNotFoundError:
                        continue

                # Collect labels from all messages in the thread
                all_labels_in_thread = set()
                for message in thread.messages:
                    all_labels_in_thread.update(message.gmail_labels)

                logger.debug(f"All unique labels found in thread: {all_labels_in_thread}")
                logger.debug(f"Resolved special folders for filtering: {resolved_special_folders}")

                # Filter out system labels
                user_labels = [
                    label for label in all_labels_in_thread 
                    if label not in resolved_special_folders
                ]
                thread.most_recent_user_labels = sorted(list(set(user_labels))) # Sort for consistent output
                logger.debug(f"Resulting user labels for thread: {thread.most_recent_user_labels}")

                return thread
            
            return None
            
    except Exception as e:
        logger.error(f"Error getting thread: {e}")
        return None

def _get_emails_sync(folder_name: str, count: int, app_settings: AppSettings, filter_by_labels: Optional[List[str]] = None) -> List[EmailMessage]:
    """
    Synchronous function to get recent emails from a specific folder, with optional label filtering.
    """
    messages = []
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            # The folder_name is the actual name, so we don't need the resolver.
            # We select it directly.
            logger.info(f"Attempting to select folder: {folder_name}")
            mail.select(f'"{folder_name}"', readonly=True)
            
            search_criteria = ['ALL']
            if filter_by_labels:
                # Gmail-specific search for labels using X-GM-RAW extension.
                # For an OR search, we wrap the label queries in {}.
                labels_query = "{" + " ".join([f"label:{label}" for label in filter_by_labels]) + "}"
                search_criteria.append(f'(X-GM-RAW "{labels_query}")')
            
            search_query_str = ' '.join(search_criteria)
            logger.info(f"Executing IMAP search in folder '{folder_name}' with query: {search_query_str}")
            typ, data = mail.uid('search', None, search_query_str)

            if typ != 'OK' or not data or not data[0]:
                logger.warning(f"No messages found in folder '{folder_name}' matching criteria: {search_query_str}")
                return []

            uids = data[0].split()
            # Get the most recent 'count' UIDs
            recent_uids = uids[-count:]
            recent_uids.reverse() # Fetch newest first

            if not recent_uids:
                return []

            for uid in recent_uids:
                # Use the existing helper to fetch the full message
                message = _fetch_single_message(mail, uid.decode(), folder_name)
                if message:
                    messages.append(message)
            return messages

    except Exception as e:
        logger.error(f"Error getting emails from folder '{folder_name}' with labels {filter_by_labels}: {e}", exc_info=True)
        return []

def _get_recent_message_ids_sync(app_settings: AppSettings, count: int = 20) -> List[str]:
    """Synchronous function to get recent Message-IDs from INBOX"""
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            inbox_folder = resolver.get_folder_by_attribute('\\Inbox')
            mail.select(f'"{inbox_folder}"', readonly=True)
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

def _get_recent_messages_from_attribute_sync(attribute: str, app_settings: AppSettings, count: int = 20) -> List[EmailMessage]:
    """Synchronous function to get recent messages from a folder identified by a special-use attribute."""
    folder = None # Define for use in exception logging
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            folder = resolver.get_folder_by_attribute(attribute)
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
                    
                    # Extract Gmail labels from header info
                    labels = []
                    labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
                    if labels_match:
                        labels_str = labels_match.group(1)
                        # This new regex handles both quoted and unquoted labels
                        labels = re.findall(r'\\?\"?([^\"\s]+)\\?\"?', labels_str)
                        labels = [label.replace('\\\\', '\\') for label in labels]

                    # Skip draft messages (no Message-ID or has \Draft label)
                    if not message_id_header or '\\Draft' in labels:
                        i += 1
                        continue
                    
                    # Determine message type based on the presence of the \Sent label
                    message_type = 'sent' if '\\Sent' in labels else 'received'

                    # Extract UID from header info
                    uid_match = re.search(r'(\d+) \(', header_info)
                    uid = uid_match.group(1) if uid_match else recent_uids[len(messages)].decode()
                    
                    # Create contextual ID
                    contextual_id = create_contextual_id(folder, uid)
                    
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
                        in_reply_to=msg.get('In-Reply-To', '').strip('<>'),
                        type=message_type
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

def _get_user_signature(app_settings: AppSettings) -> Tuple[Optional[str], Optional[str]]:
    """Get user signature from recent sent emails using Gmail signature shortcut"""
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            # Select Gmail sent folder
            sent_folder = resolver.get_folder_by_attribute('\\Sent')
            mail.select(f'"{sent_folder}"', readonly=True)
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

def _draft_reply_sync(original_message: EmailMessage, reply_body: str, app_settings: AppSettings) -> Dict[str, Any]:
    """Synchronous function to create a draft reply"""
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            # Prepare reply headers
            original_subject = original_message.subject
            reply_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
            
            # Use Reply-To header if available, otherwise From
            reply_to_email = original_message.from_
            to_email = email.utils.parseaddr(reply_to_email)[1]
            
            # Create the reply message
            reply_message = MIMEMultipart("alternative")
            reply_message["Subject"] = reply_subject
            reply_message["From"] = app_settings.IMAP_USERNAME
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
            plain_signature, html_signature = _get_user_signature(app_settings=app_settings)
            
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
            drafts_folder = resolver.get_folder_by_attribute('\\Drafts')
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

def _set_label_sync(message_id: str, label: str, app_settings: AppSettings) -> Dict[str, Any]:
    """Synchronous function to set a label for a message."""
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            # Find the message UID and mailbox
            uid, mailbox = _find_uid_by_message_id(mail, resolver, message_id)
            if not uid:
                return {"status": "error", "message": "Message not found"}

            # Select the mailbox before setting the label
            mail.select(f'"{mailbox}"', readonly=False)
            
            # Use the UID to store the label
            result = mail.uid('store', uid, '+X-GM-LABELS', f'("{label}")')
            
            if result[0] == 'OK':
                return {"status": "success", "message": f"Label '{label}' added successfully."}
            else:
                return {"status": "error", "message": f"Failed to add label: {result[1][0].decode()}"}
    except Exception as e:
        logger.error(f"Error setting label: {e}")
        return {"status": "error", "message": str(e)}

def _remove_from_inbox_sync(message_id: str, app_settings: AppSettings) -> Dict[str, Any]:
    """
    Synchronous function to remove Gmail message from inbox by moving it to All Mail.
    Uses IMAP COPY + DELETE + EXPUNGE pattern to move from current mailbox to All Mail.
    """
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            # Find message UID and mailbox
            uid, mailbox = _find_uid_by_message_id(mail, resolver, message_id)
            if not uid:
                return {"status": "error", "message": "Message not found"}
            
            # Get the All Mail folder using resolver (language-agnostic)
            try:
                destination = resolver.get_folder_by_attribute('\\All')
            except FolderNotFoundError:
                return {"status": "error", "message": "All Mail folder not found - archiving not supported"}
            
            # Select source mailbox for modification
            mail.select(f'"{mailbox}"', readonly=False)
            
            # Copy to All Mail folder (using resolver for language support)
            typ, data = mail.uid('COPY', uid, f'"{destination}"')
            if typ != 'OK':
                return {"status": "error", "message": f"Remove from inbox failed - copy to {destination} failed"}
            
            # Mark original as deleted and expunge
            mail.uid('STORE', uid, '+FLAGS', r'(\Deleted)')
            mail.expunge()
            
            return {
                "status": "success", 
                "message": f"Email removed from inbox: moved from {mailbox} to {destination}"
            }
            
    except Exception as e:
        logger.error(f"Error removing from inbox: {e}")
        return {"status": "error", "message": str(e)}

def _get_all_folders_sync(mail: imaplib.IMAP4_SSL) -> List[str]:
    """
    Synchronous function to get all folders/mailboxes.
    """
    folders = []
    try:
        typ, data = mail.list()
        if typ == 'OK':
            for item in data:
                # The response from mail.list() is a bit complex.
                # It can have different formats, so we need to parse it carefully.
                # A typical response item is: b'(\\HasNoChildren) "/" "INBOX"'
                parts = item.decode().split('"')
                if len(parts) >= 3:
                    folder_name = parts[-2]
                    # We'll skip folders that are containers for other folders and have the \Noselect attribute
                    if '\\Noselect' not in parts[0]:
                        folders.append(folder_name)
    except Exception as e:
        logger.error(f"Error fetching folders: {e}")
    
    # Let's ensure INBOX is first if it exists, as it's the most common.
    if "INBOX" in folders:
        folders.remove("INBOX")
        folders.insert(0, "INBOX")
        
    return folders

def _get_all_labels_sync(mail: imaplib.IMAP4_SSL, resolver: FolderResolver) -> List[str]:
    """
    Synchronous function to get all unique Gmail labels from a sample of recent emails.
    """
    try:
        # 1. Get the names of all special-use folders from the resolver
        special_use_folders = set()
        # Add inbox, as it's a special case
        special_use_folders.add(resolver.get_folder_by_attribute('\\Inbox'))

        for attr in resolver.SPECIAL_USE_ATTRIBUTES:
            try:
                folder_name = resolver.get_folder_by_attribute(attr)
                special_use_folders.add(folder_name)
            except FolderNotFoundError:
                # It's okay if some special folders don't exist
                pass

        # 2. Get the full list of folders from the IMAP server
        all_folders = []
        status, folder_data = mail.list()
        if status != 'OK':
            return []
        
        for item in folder_data:
            line = item.decode()
            match = re.search(r'\((?P<attributes>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)', line)
            if not match:
                continue
            
            # 3. Filter the list
            label_name = match.group('name').strip().strip('"')
            flags = match.group('attributes')

            # Exclude folders that are not selectable
            if '\\Noselect' in flags:
                continue
            
            # Exclude special use folders
            if label_name in special_use_folders:
                continue
            
            all_folders.append(label_name)
        
        return all_folders

    except Exception as e:
        logger.error(f"Error listing labels: {e}")
        return []

def _get_all_special_use_folders_sync(app_settings: AppSettings) -> List[str]:
    """
    Synchronous function to get a list of all special-use folder names.
    Leverages the FolderResolver to get language-agnostic folder names.
    """
    folders = []
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            # Also add the INBOX, which is a special case not in the attributes list
            special_folders_to_check = list(resolver.SPECIAL_USE_ATTRIBUTES) + ['\\Inbox']
            
            for attribute in special_folders_to_check:
                try:
                    folder_name = resolver.get_folder_by_attribute(attribute)
                    if folder_name not in folders:
                        folders.append(folder_name)
                except FolderNotFoundError:
                    logger.warning(f"Could not resolve special-use folder for attribute '{attribute}'. Skipping.")
                    continue
        logger.info(f"Resolved special-use folders: {folders}")
        return sorted(folders)
    except Exception as e:
        logger.error(f"Failed to get special-use folders: {e}", exc_info=True)
        return []


def _get_messages_from_folder_sync(folder_name: str, count: int, app_settings: AppSettings) -> List[EmailMessage]:
    """Synchronous function to get recent messages from a specific folder."""
    messages = []
    try:
        with imap_connection(app_settings=app_settings) as (mail, _):
            # Need to handle nested labels (e.g., "Parent/Child") for some clients
            status, _ = mail.select(f'"{folder_name}"', readonly=True)
            if status != 'OK':
                logger.warning(f"Could not select folder: {folder_name}")
                return []
                
            typ, data = mail.uid('search', None, 'ALL')
            if typ != 'OK' or not data[0]:
                return []

            uids = data[0].split()
            # Get the most recent `count` uids
            recent_uids = uids[-count:]
            
            if not recent_uids:
                return []

            uid_list_str = ','.join([uid.decode() for uid in recent_uids])
            # Fetch all messages with labels in one call
            typ, fetch_data = mail.uid('fetch', uid_list_str, '(RFC822 X-GM-LABELS)')
            if typ != 'OK' or not fetch_data:
                return []

            for item in fetch_data:
                if isinstance(item, tuple):
                    # _fetch_single_message expects UID to be passed separately, but fetch response includes it.
                    # We can parse it out, but it's easier to just call it per UID.
                    # This is less efficient than bulk processing, but re-uses code and is simple.
                    pass

            for uid in reversed(recent_uids): # Fetch newest first
                msg = _fetch_single_message(mail, uid.decode(), folder_name)
                if msg:
                    messages.append(msg)
            return messages
    except Exception as e:
        logger.error(f"Error getting messages from folder {folder_name}: {e}")
        return []


def _get_messages_from_multiple_folders_sync(folder_names: List[str], count: int, app_settings: AppSettings) -> Dict[str, List[EmailMessage]]:
    """Synchronous function to get recent messages from multiple folders using a single connection."""
    results: Dict[str, List[EmailMessage]] = {name: [] for name in folder_names}
    try:
        with imap_connection(app_settings=app_settings) as (mail, _):
            for folder_name in folder_names:
                try:
                    status, _ = mail.select(f'"{folder_name}"', readonly=True)
                    if status != 'OK':
                        logger.warning(f"Could not select folder: {folder_name}, skipping.")
                        continue
                        
                    typ, data = mail.uid('search', None, 'ALL')
                    if typ != 'OK' or not data[0]:
                        logger.info(f"No messages found in folder: {folder_name}")
                        continue

                    uids = data[0].split()
                    recent_uids = uids[-count:]
                    
                    if not recent_uids:
                        continue

                    # Fetch all messages with labels in one call
                    uid_list_str = ','.join([uid.decode() for uid in recent_uids])
                    typ, fetch_data = mail.uid('fetch', uid_list_str, '(RFC822 X-GM-LABELS)')
                    if typ != 'OK' or not fetch_data:
                        continue

                    messages = []
                    i = 0
                    # The fetch_data can contain other things besides tuples, so we iterate safely
                    while i < len(fetch_data):
                        if isinstance(fetch_data[i], tuple) and len(fetch_data[i]) >= 2:
                            header_info = fetch_data[i][0].decode() if isinstance(fetch_data[i][0], bytes) else str(fetch_data[i][0])
                            msg_bytes = fetch_data[i][1]
                            
                            # Re-use the robust parsing from the single message fetch logic
                            # We create a temporary message object to extract headers, then build the full one
                            temp_msg = email.message_from_bytes(msg_bytes)
                            message_id_header = temp_msg.get('Message-ID', '').strip('<>')
                            if not message_id_header:
                                i += 1
                                continue
                            
                            # Extract UID from header info
                            uid_match = re.search(r'(\d+) \(', header_info)
                            uid = uid_match.group(1) if uid_match else "unknown"

                            # The _fetch_single_message function is perfect for parsing the rest
                            # We can call it with the data we already have, avoiding another network call
                            # by passing a mock mail object or adapting it.
                            # For simplicity, let's replicate its parsing logic here.
                            
                            contextual_id = create_contextual_id(folder_name, uid)
                            
                            labels = []
                            labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
                            if labels_match:
                                labels_str = labels_match.group(1)
                                labels = re.findall(r'"([^"]*)"', labels_str)
                                labels = [label.replace('\\\\', '\\') for label in labels]

                            message_type = 'sent' if '\\Sent' in labels else 'received'
                            body_formats = extract_body_formats(temp_msg)

                            messages.append(EmailMessage(
                                uid=contextual_id,
                                message_id=message_id_header,
                                **{'from': temp_msg.get('From', '')},
                                to=temp_msg.get('To', ''),
                                cc=temp_msg.get('Cc', ''),
                                bcc=temp_msg.get('Bcc', ''),
                                subject=temp_msg.get('Subject', ''),
                                date=temp_msg.get('Date', ''),
                                body_raw=body_formats['raw'],
                                body_markdown=body_formats['markdown'],
                                body_cleaned=body_formats['cleaned'],
                                gmail_labels=labels,
                                references=temp_msg.get('References', ''),
                                in_reply_to=temp_msg.get('In-Reply-To', '').strip('<>'),
                                type=message_type
                            ))
                        i += 1
                    
                    # Messages are fetched in order of UID list, which is oldest to newest.
                    # We want newest first, so we reverse the final list.
                    results[folder_name] = messages[::-1]
                    logger.info(f"Fetched {len(messages)} messages from folder '{folder_name}'")

                except Exception as e:
                    logger.error(f"Error processing folder {folder_name} within multi-folder fetch: {e}")
                    continue
            return results
    except IMAPConnectionError as e:
        logger.error(f"IMAP Connection failed during multi-folder fetch: {e}")
        return {name: [] for name in folder_names} # Return empty dict on connection failure
    except Exception as e:
        logger.error(f"Unexpected error getting messages from multiple folders: {e}", exc_info=True)
        return {name: [] for name in folder_names}


# --- Async Wrappers ---

async def get_recent_inbox_message_ids(user_uuid: UUID, count: int = 20) -> List[str]:
    """Asynchronously gets recent Message-IDs from INBOX"""
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_get_recent_message_ids_sync, app_settings, count)

async def get_message_by_id(user_uuid: UUID, message_id: str) -> Optional[EmailMessage]:
    """
    Asynchronously gets a single EmailMessage by its Message-ID.
    """
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_get_message_by_id_sync, message_id, app_settings)

async def get_complete_thread(user_uuid: UUID, source_message: EmailMessage) -> Optional[EmailThread]:
    if not source_message or not source_message.message_id:
        return None
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_get_complete_thread_sync, source_message.message_id, app_settings)

async def get_recent_inbox_messages(user_uuid: UUID, count: int = 10) -> List[EmailMessage]:
    """Asynchronously gets the most recent messages from the inbox."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_get_recent_messages_from_attribute_sync, '\\Inbox', app_settings, count)

async def get_recent_sent_messages(user_uuid: UUID, count: int = 20) -> List[EmailMessage]:
    """Asynchronously gets the most recent messages from the sent folder."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_get_recent_messages_from_attribute_sync, '\\Sent', app_settings, count)

async def draft_reply(user_uuid: UUID, original_message: EmailMessage, reply_body: str) -> Dict[str, Any]:
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_draft_reply_sync, original_message, reply_body, app_settings)

async def set_label(user_uuid: UUID, message_id: str, label: str) -> Dict[str, Any]:
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    async with acquire_imap_slot(user_uuid):
        return await loop.run_in_executor(None, _set_label_sync, message_id, label, app_settings)

async def remove_from_inbox(user_uuid: UUID, message_id: str) -> Dict[str, Any]:
    """Async wrapper for removing Gmail message from inbox by moving to All Mail"""
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_remove_from_inbox_sync, message_id, app_settings)

async def get_emails(user_uuid: UUID, folder_name: str, count: int = 10, filter_by_labels: Optional[List[str]] = None) -> List[EmailMessage]:
    """Asynchronous wrapper for getting emails from a folder with optional label filtering."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    async with acquire_imap_slot(user_uuid):
        return await loop.run_in_executor(
            None,
            _get_emails_sync,
            folder_name,
            count,
            app_settings,
            filter_by_labels
        )

async def get_all_folders(user_uuid: UUID) -> List[str]:
    """Asynchronous wrapper for getting all folders."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    async with acquire_imap_slot(user_uuid):
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            # We don't need the resolver here, but the connection manager provides it.
            return await loop.run_in_executor(None, _get_all_folders_sync, mail)

async def get_all_labels(user_uuid: UUID) -> List[str]:
    """Asynchronously gets all labels from the IMAP server."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    try:
        async with acquire_imap_slot(user_uuid):
            with imap_connection(app_settings=app_settings) as (mail, resolver):
                return await asyncio.to_thread(_get_all_labels_sync, mail, resolver)
    except IMAPConnectionError:
        logger.error(f"IMAP connection failed when getting all labels for user {user_uuid}")
        raise  # Re-raise the connection error to be handled by the caller
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting all labels: {e}")
        return []

async def get_all_special_use_folders(user_uuid: UUID) -> List[str]:
    """
    Asynchronous wrapper to get a list of all special-use folder names.
    """
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    async with acquire_imap_slot(user_uuid):
        return await loop.run_in_executor(None, _get_all_special_use_folders_sync, app_settings)


async def get_messages_from_folder(user_uuid: UUID, folder_name: str, count: int = 10) -> List[EmailMessage]:
    """Asynchronously gets recent messages from a specific folder/label."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_get_messages_from_folder_sync, folder_name, count, app_settings)

async def get_messages_from_multiple_folders(user_uuid: UUID, folder_names: List[str], count: int = 10) -> Dict[str, List[EmailMessage]]:
    """Asynchronously gets recent messages from a list of specific folders/labels using a single connection."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_get_messages_from_multiple_folders_sync, folder_names, count, app_settings)

async def get_recent_threads_bulk(
    target_thread_count: int = 50, 
    max_age_months: int = 6, 
    source_folder_attribute: str = '\\Sent',
    user_uuid: Optional[UUID] = None
) -> Tuple[List[EmailThread], Dict[str, float]]:
    """
    High-performance bulk retrieval of recent email threads.
    
    This is a pass-through to the optimized bulk fetching implementation,
    which uses a single persistent connection and advanced IMAP features
    to discover and fetch threads efficiently.

    Args:
        target_thread_count (int, optional): The target number of threads to fetch. Defaults to 50.
        max_age_months (int, optional): The maximum age of emails to consider. Defaults to 6.
        source_folder_attribute (str, optional): The special-use attribute for the folder to search. Defaults to '\\Sent'.

    Returns:
        Tuple[List[EmailThread], Dict[str, float]]: A tuple containing the list of threads and performance timing data.
    """
    # Use the bulk optimized fetch with concurrency guard
    async with acquire_imap_slot(user_uuid) if user_uuid else asyncio.dummy_context():
        return await fetch_recent_threads_bulk(
        target_thread_count=target_thread_count,
        max_age_months=max_age_months,
        source_folder_attribute=source_folder_attribute,
        user_uuid=user_uuid
    )

def _decode_header_value(value: str) -> str:
    try:
        parts = decode_header(value)
        decoded = ''.join(
            (part.decode(enc or 'utf-8') if isinstance(part, bytes) else part)
            for part, enc in parts
        )
        return decoded
    except Exception:
        return value


def _list_headers_sync(folder_name: str, count: int, app_settings: AppSettings, filter_by_labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Fetches lightweight headers for recent messages without bodies."""
    results: List[Dict[str, Any]] = []
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            mail.select(f'"{folder_name}"', readonly=True)

            search_criteria = ['ALL']
            if filter_by_labels:
                labels_query = "{" + " ".join([f"label:{label}" for label in filter_by_labels]) + "}"
                search_criteria.append(f'(X-GM-RAW "{labels_query}")')
            search_query_str = ' '.join(search_criteria)
            typ, data = mail.uid('search', None, search_query_str)
            if typ != 'OK' or not data or not data[0]:
                return []

            uids = data[0].split()
            recent_uids = uids[-count:]
            recent_uids.reverse()
            if not recent_uids:
                return []

            # Batch FETCH headers for all requested UIDs in a single round trip
            uid_list_str = ','.join(uid.decode() if isinstance(uid, (bytes, bytearray)) else str(uid) for uid in recent_uids)
            typ, fetch_data = mail.uid('fetch', uid_list_str, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT FROM TO DATE)] X-GM-LABELS)')
            if typ != 'OK' or not fetch_data:
                return []

            i = 0
            while i < len(fetch_data):
                part = fetch_data[i]
                if isinstance(part, tuple) and len(part) >= 2:
                    meta = part[0]
                    body = part[1]
                    headers_text = ''
                    labels_list: List[str] = []

                    try:
                        headers_text = body.decode('utf-8', errors='replace')
                    except Exception:
                        headers_text = str(body)

                    # Extract X-GM-LABELS from meta if present
                    try:
                        meta_bytes = meta if isinstance(meta, (bytes, bytearray)) else str(meta).encode('utf-8')
                        meta_str = meta_bytes.decode('utf-8', errors='ignore')
                        start = meta_str.find('X-GM-LABELS (')
                        if start != -1:
                            end = meta_str.find(')', start)
                            if end != -1:
                                raw = meta_str[start + len('X-GM-LABELS ('):end]
                                labels_list = [l.strip('"') for l in raw.split(' ') if l]
                    except Exception:
                        pass

                    # Parse fields from headers
                    message_id = ''
                    subject = ''
                    from_ = ''
                    to = ''
                    date = ''
                    for line in headers_text.splitlines():
                        if line.lower().startswith('message-id:'):
                            message_id = line.split(':', 1)[1].strip().strip('<>')
                        elif line.lower().startswith('subject:'):
                            subject = _decode_header_value(line.split(':', 1)[1].strip())
                        elif line.lower().startswith('from:'):
                            from_ = _decode_header_value(line.split(':', 1)[1].strip())
                        elif line.lower().startswith('to:'):
                            to = _decode_header_value(line.split(':', 1)[1].strip())
                        elif line.lower().startswith('date:'):
                            date = line.split(':', 1)[1].strip()

                    # Extract UID from meta
                    uid_val = None
                    try:
                        if isinstance(meta, (bytes, bytearray)):
                            uid_match = re.search(rb'\b(\d+) \(', meta)
                            uid_val = uid_match.group(1).decode() if uid_match else None
                        else:
                            uid_match_txt = re.search(r'\b(\d+) \(', str(meta))
                            uid_val = uid_match_txt.group(1) if uid_match_txt else None
                    except Exception:
                        uid_val = None

                    if message_id and uid_val:
                        results.append({
                            'uid': create_contextual_id(folder_name, uid_val),
                            'message_id': message_id,
                            'subject': subject,
                            'from': from_,
                            'to': to,
                            'date': date,
                            'gmail_labels': labels_list,
                        })
                i += 1

        return results
    except Exception as e:
        logger.error(f"Error listing headers from folder '{folder_name}': {e}", exc_info=True)
        return []


async def list_headers(user_uuid: UUID, folder_name: str, count: int = 50, filter_by_labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    async with acquire_imap_slot(user_uuid):
        return await loop.run_in_executor(None, _list_headers_sync, folder_name, count, app_settings, filter_by_labels)


def _list_headers_multi_with_counts_sync(folder_names: List[str], count: int, app_settings: AppSettings, filter_by_labels: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Single-connection, multi-folder headers-only listing with totals.
    Returns {'items': List[header_dict], 'total': int} where total is the sum of SEARCH counts across folders.
    """
    items: List[Dict[str, Any]] = []
    total = 0
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            search_criteria_parts = ['ALL']
            if filter_by_labels:
                labels_query = "{" + " ".join([f"label:{label}" for label in filter_by_labels]) + "}"
                search_criteria_parts.append(f'(X-GM-RAW "{labels_query}")')
            search_query_str = ' '.join(search_criteria_parts)

            for folder in folder_names:
                try:
                    mail.select(f'"{folder}"', readonly=True)
                    typ, data = mail.uid('search', None, search_query_str)
                    if typ != 'OK' or not data or not data[0]:
                        continue
                    uids = data[0].split()
                    total += len(uids)
                    if not uids:
                        continue
                    # Take only the most recent `count` UIDs for this folder
                    recent_uids = uids[-count:]
                    if not recent_uids:
                        continue
                    uid_list_str = ','.join(uid.decode() if isinstance(uid, (bytes, bytearray)) else str(uid) for uid in recent_uids)
                    typ_f, fetch_data = mail.uid('fetch', uid_list_str, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT FROM TO DATE)] X-GM-LABELS)')
                    if typ_f != 'OK' or not fetch_data:
                        continue
                    i = 0
                    while i < len(fetch_data):
                        part = fetch_data[i]
                        if isinstance(part, tuple) and len(part) >= 2:
                            meta = part[0]
                            body = part[1]
                            headers_text = ''
                            labels_list: List[str] = []

                            try:
                                headers_text = body.decode('utf-8', errors='replace')
                            except Exception:
                                headers_text = str(body)

                            # Extract labels from meta
                            try:
                                meta_bytes = meta if isinstance(meta, (bytes, bytearray)) else str(meta).encode('utf-8')
                                meta_str = meta_bytes.decode('utf-8', errors='ignore')
                                start = meta_str.find('X-GM-LABELS (')
                                if start != -1:
                                    end = meta_str.find(')', start)
                                    if end != -1:
                                        raw = meta_str[start + len('X-GM-LABELS ('):end]
                                        labels_list = [l.strip('"') for l in raw.split(' ') if l]
                            except Exception:
                                pass

                            # Extract UID from meta
                            uid_val = None
                            try:
                                if isinstance(meta, (bytes, bytearray)):
                                    uid_match = re.search(rb'\b(\d+) \(', meta)
                                    uid_val = uid_match.group(1).decode() if uid_match else None
                                else:
                                    uid_match_txt = re.search(r'\b(\d+) \(', str(meta))
                                    uid_val = uid_match_txt.group(1) if uid_match_txt else None
                            except Exception:
                                uid_val = None

                            # Parse header fields
                            message_id = ''
                            subject = ''
                            from_ = ''
                            to = ''
                            date = ''
                            for line in headers_text.splitlines():
                                if line.lower().startswith('message-id:'):
                                    message_id = line.split(':', 1)[1].strip().strip('<>')
                                elif line.lower().startswith('subject:'):
                                    subject = _decode_header_value(line.split(':', 1)[1].strip())
                                elif line.lower().startswith('from:'):
                                    from_ = _decode_header_value(line.split(':', 1)[1].strip())
                                elif line.lower().startswith('to:'):
                                    to = _decode_header_value(line.split(':', 1)[1].strip())
                                elif line.lower().startswith('date:'):
                                    date = line.split(':', 1)[1].strip()

                            if message_id and uid_val:
                                items.append({
                                    'uid': create_contextual_id(folder, uid_val),
                                    'message_id': message_id,
                                    'subject': subject,
                                    'from': from_,
                                    'to': to,
                                    'date': date,
                                    'gmail_labels': labels_list,
                                })
                        i += 1
                except Exception:
                    continue
        return {'items': items, 'total': total}
    except Exception as e:
        logger.error(f"Error listing headers across folders: {e}", exc_info=True)
        return {'items': [], 'total': 0}


async def list_headers_multi_with_counts(user_uuid: UUID, folder_names: List[str], count: int = 50, filter_by_labels: Optional[List[str]] = None) -> Dict[str, Any]:
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    async with acquire_imap_slot(user_uuid):
        return await loop.run_in_executor(None, _list_headers_multi_with_counts_sync, folder_names, count, app_settings, filter_by_labels)


def _get_message_by_contextual_uid_sync(contextual_uid: str, app_settings: AppSettings) -> Optional[EmailMessage]:
    try:
        encoded_mailbox, uid = contextual_uid.split(':', 1)
        mailbox = base64.b64decode(encoded_mailbox.encode('utf-8')).decode('utf-8')
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            mail.select(f'"{mailbox}"', readonly=True)
            msg = _fetch_single_message(mail, uid, mailbox)
            return msg
    except Exception as e:
        logger.error(f"Error fetching by contextual uid {contextual_uid}: {e}")
        return None


async def get_message_by_contextual_uid(user_uuid: UUID, contextual_uid: str) -> Optional[EmailMessage]:
    app_settings = load_app_settings(user_uuid=user_uuid)
    async with acquire_imap_slot(user_uuid):
        return await asyncio.to_thread(_get_message_by_contextual_uid_sync, contextual_uid, app_settings)


def _list_recent_uids_sync(folder_name: str, count: int, app_settings: AppSettings, filter_by_labels: Optional[List[str]] = None) -> List[str]:
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            mail.select(f'"{folder_name}"', readonly=True)
            search_criteria = ['ALL']
            if filter_by_labels:
                labels_query = "{" + " ".join([f"label:{label}" for label in filter_by_labels]) + "}"
                search_criteria.append(f'(X-GM-RAW "{labels_query}")')
            search_query_str = ' '.join(search_criteria)
            typ, data = mail.uid('search', None, search_query_str)
            if typ != 'OK' or not data or not data[0]:
                return []
            uids = data[0].split()
            recent_uids = list(reversed(uids[-count:]))
            return [create_contextual_id(folder_name, uid.decode() if isinstance(uid, (bytes, bytearray)) else str(uid)) for uid in recent_uids]
    except Exception as e:
        logger.error(f"Error listing recent uids for folder '{folder_name}': {e}")
        return []


async def list_recent_uids(user_uuid: UUID, folder_name: str, count: int = 50, filter_by_labels: Optional[List[str]] = None) -> List[str]:
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    async with acquire_imap_slot(user_uuid):
        return await loop.run_in_executor(None, _list_recent_uids_sync, folder_name, count, app_settings, filter_by_labels)

def _count_uids_sync(folder_name: str, app_settings: AppSettings, filter_by_labels: Optional[List[str]] = None) -> int:
    """Counts UIDs matching the search in a folder without fetching any message data."""
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            mail.select(f'"{folder_name}"', readonly=True)
            search_criteria = ['ALL']
            if filter_by_labels:
                labels_query = "{" + " ".join([f"label:{label}" for label in filter_by_labels]) + "}"
                search_criteria.append(f'(X-GM-RAW "{labels_query}")')
            search_query_str = ' '.join(search_criteria)
            typ, data = mail.uid('search', None, search_query_str)
            if typ != 'OK' or not data or not data[0]:
                return 0
            return len(data[0].split())
    except Exception as e:
        logger.error(f"Error counting UIDs in folder '{folder_name}': {e}", exc_info=True)
        return 0


async def count_uids(user_uuid: UUID, folder_name: str, filter_by_labels: Optional[List[str]] = None) -> int:
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    async with acquire_imap_slot(user_uuid):
        return await loop.run_in_executor(None, _count_uids_sync, folder_name, app_settings, filter_by_labels)


# --- Bulk Export (Single Connection, Deduplicate by Thread) ---

def _parse_thrid_from_meta(meta_bytes: bytes) -> Optional[str]:
    try:
        match = re.search(rb'X-GM-THRID (\d+)', meta_bytes)
        if match:
            return match.group(1).decode()
    except Exception:
        pass
    return None

def _decode_contextual_uid(contextual_uid: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        encoded_mailbox, uid = contextual_uid.split(':', 1)
        mailbox = base64.b64decode(encoded_mailbox.encode('utf-8')).decode('utf-8')
        return mailbox, uid
    except Exception:
        return None, None

def _resolve_thread_ids_single_connection(
    mail: imaplib.IMAP4_SSL,
    resolver: FolderResolver,
    identifiers: List[str]
) -> Tuple[Set[str], Dict[str, List[str]]]:
    """
    Resolve a mixed list of Message-IDs and contextual UIDs to Gmail thread IDs (X-GM-THRID)
    using a single IMAP connection. Returns a set of unique thread ids and a mapping
    thrid -> list of identifiers that map to that thread.
    """
    logger.info(f"[bulk] Resolving thread IDs for {len(identifiers)} identifiers")
    thrids: Set[str] = set()
    thrid_to_identifiers: DefaultDict[str, List[str]] = defaultdict(list)

    # 1) Partition identifiers
    contextual_uids: DefaultDict[str, List[str]] = defaultdict(list)  # mailbox -> [uid]
    message_ids: List[str] = []
    for ident in identifiers:
        if ':' in ident and len(ident.split(':', 1)[0]) > 0:
            mailbox, uid = _decode_contextual_uid(ident)
            if mailbox and uid:
                contextual_uids[mailbox].append(uid)
            else:
                # fallback to treating as message-id if malformed
                message_ids.append(ident)
        else:
            message_ids.append(ident)
    logger.info(f"[bulk] Partitioned identifiers: {sum(len(v) for v in contextual_uids.values())} contextual UIDs across {len(contextual_uids)} mailbox(es), {len(message_ids)} Message-IDs")

    # 2) Resolve thrids for contextual uids in batches per mailbox
    for mailbox, uids in contextual_uids.items():
        try:
            mail.select(f'"{mailbox}"', readonly=True)
            # Batch fetch X-GM-THRID for all uids in this mailbox
            uid_list = ','.join(uids)
            typ, data = mail.uid('fetch', uid_list, '(X-GM-THRID)')
            logger.debug(f"[bulk] Batch FETCH X-GM-THRID typ={typ}, parts={len(data) if data else 0} in mailbox {mailbox}")
            parsed_any = False
            resolved_uids: Set[str] = set()
            if typ == 'OK' and data:
                # Parse results; map each UID to its thrid
                for part in data:
                    meta: Optional[bytes] = None
                    if isinstance(part, tuple) and isinstance(part[0], (bytes, bytearray)):
                        meta = part[0]
                    elif isinstance(part, (bytes, bytearray)):
                        meta = part
                    if not meta:
                        continue
                    # Extract UID and THRID
                    uid_match = re.search(rb'\b(\d+) \(', meta)
                    uid_str = uid_match.group(1).decode() if uid_match else None
                    thrid = _parse_thrid_from_meta(meta)
                    if uid_str and thrid:
                        parsed_any = True
                        thrids.add(thrid)
                        contextual_identifier = create_contextual_id(mailbox, uid_str)
                        thrid_to_identifiers[thrid].append(contextual_identifier)
                        resolved_uids.add(uid_str)
            logger.debug(f"[bulk] Mailbox {mailbox}: batch parsed_any={parsed_any}, current thrids={len(thrids)}")
            # Fallback to per-UID fetch if batch failed or parsed nothing
            if not parsed_any:
                for uid in uids:
                    try:
                        typ_one, data_one = mail.uid('fetch', uid, '(X-GM-THRID)')
                        logger.debug(f"[bulk] Per-UID FETCH X-GM-THRID typ={typ_one} parts={len(data_one) if data_one else 0} for uid={uid} in {mailbox}")
                        if typ_one != 'OK' or not data_one:
                            continue
                        meta_one: Optional[bytes] = None
                        first = data_one[0]
                        if isinstance(first, tuple) and isinstance(first[0], (bytes, bytearray)):
                            meta_one = first[0]
                        elif isinstance(first, (bytes, bytearray)):
                            meta_one = first
                        if not meta_one:
                            continue
                        thrid = _parse_thrid_from_meta(meta_one)
                        if not thrid:
                            continue
                        thrids.add(thrid)
                        contextual_identifier = create_contextual_id(mailbox, uid)
                        thrid_to_identifiers[thrid].append(contextual_identifier)
                        resolved_uids.add(uid)
                    except Exception:
                        continue
            logger.info(f"[bulk] Mailbox {mailbox}: resolved {len(resolved_uids)}/{len(uids)} UIDs -> cumulative unique thrids={len(thrids)}")

            # Derive Message-IDs for unresolved UIDs to allow Message-ID-based resolution later
            unresolved = [uid for uid in uids if uid not in resolved_uids]
            if unresolved:
                logger.info(f"[bulk] Mailbox {mailbox}: attempting to derive Message-IDs for {len(unresolved)} unresolved UIDs")
                for uid in unresolved:
                    try:
                        typ_mid, data_mid = mail.uid('fetch', uid, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])')
                        if typ_mid != 'OK' or not data_mid:
                            continue
                        header_blob: Optional[bytes] = None
                        for part in data_mid:
                            if isinstance(part, tuple) and isinstance(part[1], (bytes, bytearray)):
                                header_blob = part[1]
                                break
                        if not header_blob:
                            continue
                        headers_text = header_blob.decode('utf-8', errors='replace')
                        msgid_match = re.search(r'Message-ID:\s*<([^>]+)>', headers_text, re.IGNORECASE)
                        if msgid_match:
                            mid = msgid_match.group(1)
                            message_ids.append(mid)
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Failed to resolve thread IDs in mailbox '{mailbox}': {e}")
            continue

    # 3) Resolve thrids for Message-IDs in All Mail preferably
    all_mailbox = None
    try:
        all_mailbox = resolver.get_folder_by_attribute('\\All')
    except FolderNotFoundError:
        # Fall back to Inbox and Sent search
        all_mailbox = None

    if all_mailbox and message_ids:
        try:
            mail.select(f'"{all_mailbox}"', readonly=True)
            resolved_in_all = 0
            for message_id in message_ids:
                try:
                    typ, data = mail.uid('search', None, f'(HEADER Message-ID "{message_id}")')
                    if typ == 'OK' and data and data[0]:
                        uid = data[0].split()[0].decode()
                        # Fetch X-GM-THRID for this uid
                        typ2, data2 = mail.uid('fetch', uid, '(X-GM-THRID)')
                        if typ2 == 'OK' and data2 and isinstance(data2[0], tuple):
                            meta = data2[0][0] if isinstance(data2[0][0], (bytes, bytearray)) else None
                            if meta:
                                thrid = _parse_thrid_from_meta(meta)
                                if thrid:
                                    thrids.add(thrid)
                                    thrid_to_identifiers[thrid].append(message_id)
                                    resolved_in_all += 1
                except Exception as e:
                    logger.warning(f"Search by Message-ID failed in All Mail for {message_id}: {e}")
                    continue
            logger.info(f"[bulk] Resolved {resolved_in_all} Message-IDs in All Mail -> cumulative unique thrids={len(thrids)}")
        except Exception as e:
            logger.warning(f"Could not select All Mail '{all_mailbox}': {e}")

    # If some message_ids remain unresolved and All Mail was not available or failed,
    # do a best-effort search in Inbox then Sent
    if (not all_mailbox) and message_ids:
        for attr in ['\\Inbox', '\\Sent']:
            try:
                folder = resolver.get_folder_by_attribute(attr)
                mail.select(f'"{folder}"', readonly=True)
                unresolved = []
                resolved_here = 0
                for message_id in message_ids:
                    try:
                        typ, data = mail.uid('search', None, f'(HEADER Message-ID "{message_id}")')
                        if typ == 'OK' and data and data[0]:
                            uid = data[0].split()[0].decode()
                            typ2, data2 = mail.uid('fetch', uid, '(X-GM-THRID)')
                            meta = None
                            if typ2 == 'OK' and data2 and isinstance(data2[0], tuple):
                                meta = data2[0][0] if isinstance(data2[0][0], (bytes, bytearray)) else None
                            if meta:
                                thrid = _parse_thrid_from_meta(meta)
                                if thrid and thrid not in thrids:
                                    thrids.add(thrid)
                                    thrid_to_identifiers[thrid].append(message_id)
                                    resolved_here += 1
                                    continue
                        unresolved.append(message_id)
                    except Exception:
                        unresolved.append(message_id)
                message_ids = unresolved
                logger.info(f"[bulk] Folder {folder}: resolved {resolved_here} Message-IDs, remaining unresolved={len(message_ids)}; cumulative thrids={len(thrids)}")
                if not message_ids:
                    break
            except Exception:
                continue

    if not thrids:
        logger.warning("[bulk] No thread IDs were resolved from provided identifiers.")
    return thrids, thrid_to_identifiers

def _fetch_threads_by_thrids_single_connection(
    mail: imaplib.IMAP4_SSL,
    resolver: FolderResolver,
    thrids: Set[str],
    thrid_to_identifiers: Optional[Dict[str, List[str]]] = None,
    total_identifiers: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    progress_completed_ref: Optional[Dict[str, int]] = None,
) -> List[EmailThread]:
    logger.info(f"[bulk] Fetching {len(thrids)} unique thread(s)")
    threads: List[EmailThread] = []

    # Prefer All Mail for thread-wide operations
    target_mailbox = None
    try:
        target_mailbox = resolver.get_folder_by_attribute('\\All')
    except FolderNotFoundError:
        # Fallback: use Inbox
        try:
            target_mailbox = resolver.get_folder_by_attribute('\\Inbox')
        except FolderNotFoundError:
            target_mailbox = 'INBOX'

    try:
        mail.select(f'"{target_mailbox}"', readonly=True)
    except Exception as e:
        logger.warning(f"Could not select target mailbox '{target_mailbox}': {e}")
        return threads

    for thrid in thrids:
        try:
            typ, data = mail.uid('search', None, f'(X-GM-THRID {thrid})')
            if typ != 'OK' or not data or not data[0]:
                logger.debug(f"[bulk] No UIDs found for thrid={thrid} in {target_mailbox}")
                continue
            thread_uids = [uid.decode() for uid in data[0].split()]
            if not thread_uids:
                continue

            uid_list = ','.join(thread_uids)
            typ2, fetch_data = mail.uid('fetch', uid_list, '(RFC822 X-GM-LABELS)')
            if typ2 != 'OK' or not fetch_data:
                logger.debug(f"[bulk] FETCH returned no data for thrid={thrid}")
                continue

            messages: List[EmailMessage] = []
            i = 0
            while i < len(fetch_data):
                part = fetch_data[i]
                if isinstance(part, tuple) and len(part) >= 2:
                    header_info = part[0].decode() if isinstance(part[0], bytes) else str(part[0])
                    msg = email.message_from_bytes(part[1])
                    message_id_header = msg.get('Message-ID', '').strip('<>')

                    # Extract labels
                    labels: List[str] = []
                    labels_match = re.search(r'X-GM-LABELS \(([^)]+)\)', header_info)
                    if labels_match:
                        labels_str = labels_match.group(1)
                        matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|(\S+)', labels_str)
                        raw_labels = [g1 or g2 for g1, g2 in matches]
                        labels = [label.replace('\\\\', '\\') for label in raw_labels]

                    # Skip drafts or missing message-id
                    if not message_id_header or '\\Draft' in labels:
                        i += 1
                        continue

                    # Determine message type
                    message_type = 'sent' if '\\Sent' in labels else 'received'

                    # Extract UID from header info
                    uid_match = re.search(r'(\d+) \(', header_info)
                    uid_val = uid_match.group(1) if uid_match else thread_uids[len(messages)]

                    # Build contextual ID from target_mailbox for consistency
                    contextual_id = create_contextual_id(target_mailbox, uid_val)

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
                        in_reply_to=msg.get('In-Reply-To', '').strip('<>'),
                        type=message_type
                    ))
                i += 1

            if messages:
                thread = EmailThread.from_messages(messages, thrid)
                # Compute user-defined labels across thread (filter out system folders)
                all_special_use_attributes = list(resolver.SPECIAL_USE_ATTRIBUTES) + list(resolver.FALLBACK_MAP.keys())
                resolved_special_folders = set()
                for attr in all_special_use_attributes:
                    try:
                        resolved_special_folders.add(attr)
                        resolved_special_folders.add(resolver.get_folder_by_attribute(attr))
                    except FolderNotFoundError:
                        continue

                all_labels_in_thread = set()
                for message in thread.messages:
                    all_labels_in_thread.update(message.gmail_labels)
                user_labels = [
                    label for label in all_labels_in_thread
                    if label not in resolved_special_folders
                ]
                thread.most_recent_user_labels = sorted(list(set(user_labels)))

                threads.append(thread)
                logger.info(f"[bulk] Built thread thrid={thrid} with {len(thread.messages)} messages")

                # Per-thread progress update if mapping and callback provided
                if progress_callback is not None and thrid_to_identifiers is not None and progress_completed_ref is not None and total_identifiers is not None:
                    try:
                        inc = len(thrid_to_identifiers.get(thrid, []))
                        progress_completed_ref['completed'] = min(
                            total_identifiers,
                            progress_completed_ref.get('completed', 0) + (inc if inc > 0 else 1)
                        )
                        progress_callback(total_identifiers, progress_completed_ref['completed'])
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Failed to fetch thread {thrid}: {e}")
            continue

    return threads

def _build_export_dataset_from_threads(threads: List[EmailThread]) -> List[Dict[str, Any]]:
    dataset: List[Dict[str, Any]] = []
    for thread in threads:
        dataset.append({
            "thread_markdown": thread.markdown,
            "thread_subject": thread.subject,
            "thread_participants": thread.participants,
            "most_recent_user_labels": thread.most_recent_user_labels,
        })
    logger.info(f"[bulk] Built dataset with {len(dataset)} thread item(s)")
    return dataset

def _export_threads_dataset_bulk_sync(
    identifiers: List[str],
    app_settings: AppSettings,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[Dict[str, Any]]:
    """
    Single-connection bulk export. Deduplicates by Gmail thread id. Accepts Message-IDs
    and contextual UIDs. Reports progress in terms of identifiers processed, grouped per thread.
    """
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            total = len(identifiers)
            logger.info(f"[bulk] Starting export for {total} identifiers")
            if progress_callback:
                try:
                    progress_callback(total, 0)
                except Exception:
                    pass

            # Interleaved resolve+fetch in batches of N
            BATCH_SIZE = 20
            dataset: List[Dict[str, Any]] = []
            seen_thrids: Set[str] = set()
            thrid_to_identifiers: DefaultDict[str, List[str]] = defaultdict(list)
            progress_state = {'completed': 0}

            # Partition identifiers
            contextual_uids: DefaultDict[str, List[str]] = defaultdict(list)
            message_ids: List[str] = []
            for ident in identifiers:
                if ':' in ident and len(ident.split(':', 1)[0]) > 0:
                    mailbox, uid = _decode_contextual_uid(ident)
                    if mailbox and uid:
                        contextual_uids[mailbox].append(uid)
                    else:
                        # fallback to treating as message-id if malformed
                        message_ids.append(ident)
                else:
                    message_ids.append(ident)
            logger.info(f"[bulk] Partitioned identifiers: {sum(len(v) for v in contextual_uids.values())} contextual UIDs across {len(contextual_uids)} mailbox(es), {len(message_ids)} Message-IDs")
            logger.info(f"[export_debug] Received {len(message_ids)} message IDs to process. Sample: {message_ids[:5]}")

            # Helper to fetch a batch of thrids and append to dataset with progress
            def _flush_batch(thrid_batch: List[str]) -> None:
                nonlocal dataset
                if not thrid_batch:
                    return
                threads = _fetch_threads_by_thrids_single_connection(
                    mail,
                    resolver,
                    set(thrid_batch),
                    thrid_to_identifiers=thrid_to_identifiers,
                    total_identifiers=total,
                    progress_callback=progress_callback,
                    progress_completed_ref=progress_state,
                )
                if threads:
                    dataset.extend(_build_export_dataset_from_threads(threads))

            # 1) Resolve contextual UIDs mailbox-by-mailbox, flushing every BATCH_SIZE new thrids
            for mailbox, uids in contextual_uids.items():
                try:
                    mail.select(f'"{mailbox}"', readonly=True)
                    batch_thrids: List[str] = []
                    # process in chunks to keep FETCH manageable
                    CHUNK = 100
                    for i in range(0, len(uids), CHUNK):
                        uid_slice = uids[i:i+CHUNK]
                        uid_list = ','.join(uid_slice)
                        typ, data = mail.uid('fetch', uid_list, '(X-GM-THRID)')
                        logger.debug(f"[bulk] Batch FETCH X-GM-THRID typ={typ}, parts={len(data) if data else 0} in mailbox {mailbox}")
                        # Parse batch results
                        resolved_in_batch: Set[str] = set()
                        if typ == 'OK' and data:
                            for part in data:
                                meta: Optional[bytes] = None
                                if isinstance(part, tuple) and isinstance(part[0], (bytes, bytearray)):
                                    meta = part[0]
                                elif isinstance(part, (bytes, bytearray)):
                                    meta = part
                                if not meta:
                                    continue
                                uid_match = re.search(rb'\b(\d+) \(', meta)
                                uid_str = uid_match.group(1).decode() if uid_match else None
                                thrid = _parse_thrid_from_meta(meta)
                                if uid_str and thrid and thrid not in seen_thrids:
                                    seen_thrids.add(thrid)
                                    batch_thrids.append(thrid)
                                    thrid_to_identifiers[thrid].append(create_contextual_id(mailbox, uid_str))
                                    resolved_in_batch.add(uid_str)
                        # per-UID fallback for unresolved in slice
                        unresolved = [uid for uid in uid_slice if uid not in resolved_in_batch]
                        if unresolved:
                            for uid in unresolved:
                                try:
                                    typ_one, data_one = mail.uid('fetch', uid, '(X-GM-THRID)')
                                    if typ_one != 'OK' or not data_one:
                                        continue
                                    meta_one: Optional[bytes] = None
                                    first = data_one[0]
                                    if isinstance(first, tuple) and isinstance(first[0], (bytes, bytearray)):
                                        meta_one = first[0]
                                    elif isinstance(first, (bytes, bytearray)):
                                        meta_one = first
                                    if not meta_one:
                                        continue
                                    thrid = _parse_thrid_from_meta(meta_one)
                                    if thrid and thrid not in seen_thrids:
                                        seen_thrids.add(thrid)
                                        batch_thrids.append(thrid)
                                        thrid_to_identifiers[thrid].append(create_contextual_id(mailbox, uid))
                                except Exception:
                                    continue

                        logger.info(f"[bulk] Mailbox {mailbox}: resolved {len(resolved_in_batch) + (len(unresolved) if unresolved else 0)} items in chunk; total unique thrids so far={len(seen_thrids)}")

                        # Flush when batch reaches BATCH_SIZE
                        if len(batch_thrids) >= BATCH_SIZE:
                            current_mailbox = mailbox
                            _flush_batch(batch_thrids[:BATCH_SIZE])
                            batch_thrids = batch_thrids[BATCH_SIZE:]
                            # Re-select the mailbox after fetching threads (fetch switches to All Mail)
                            try:
                                mail.select(f'"{current_mailbox}"', readonly=True)
                            except Exception:
                                pass

                    # Flush any remaining thrids for this mailbox
                    if batch_thrids:
                        current_mailbox = mailbox
                        _flush_batch(batch_thrids)
                        try:
                            mail.select(f'"{current_mailbox}"', readonly=True)
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"[bulk] Error processing mailbox {mailbox}: {e}")
                    continue

            # 2) If there are Message-IDs (or derived from unresolved), resolve in All Mail and flush every BATCH_SIZE
            if message_ids:
                # Define folders to search for Message-IDs, in order of preference
                mailboxes_to_search = []
                for attr in ['\\All', '\\Inbox', '\\Sent']:
                    try:
                        folder = resolver.get_folder_by_attribute(attr)
                        mailboxes_to_search.append(folder)
                    except FolderNotFoundError:
                        logger.warning(f"[export_debug] Could not resolve folder for attribute '{attr}', skipping.")
                
                # Keep track of which message IDs have been found
                resolved_mids = set()

                for mailbox in mailboxes_to_search:
                    remaining_mids = [mid for mid in message_ids if mid not in resolved_mids]
                    if not remaining_mids:
                        break
                    
                    try:
                        mail.select(f'"{mailbox}"', readonly=True)
                        batch_thrids: List[str] = []

                        for mid in remaining_mids:
                            try:
                                typ, data = mail.uid('search', None, f'(HEADER Message-ID "{mid}")')
                                
                                if typ == 'OK' and data and data[0]:
                                    uid = data[0].split()[0].decode()
                                    
                                    typ2, data2 = mail.uid('fetch', uid, '(X-GM-THRID)')
                                    meta = None
                                    
                                    # Handle different IMAP response formats for the FETCH command
                                    if typ2 == 'OK' and data2:
                                        first_part = data2[0]
                                        if isinstance(first_part, tuple) and isinstance(first_part[0], (bytes, bytearray)):
                                            # Expected format: [(b'meta', b'data')]
                                            meta = first_part[0]
                                        elif isinstance(first_part, (bytes, bytearray)):
                                            # Alternative format seen in logs: [b'meta']
                                            meta = first_part

                                    if meta:
                                        thrid = _parse_thrid_from_meta(meta)
                                        if thrid and thrid not in seen_thrids:
                                            seen_thrids.add(thrid)
                                            batch_thrids.append(thrid)
                                            thrid_to_identifiers[thrid].append(mid)
                                            resolved_mids.add(mid) # Mark this Message-ID as resolved
                                
                                # Flush on size
                                if len(batch_thrids) >= BATCH_SIZE:
                                    _flush_batch(batch_thrids)
                                    batch_thrids = []
                                    # After fetching, re-select the search mailbox
                                    mail.select(f'"{mailbox}"', readonly=True)
                            except Exception as e:
                                continue
                        
                        if batch_thrids:
                            _flush_batch(batch_thrids)
                    except Exception as e:
                        logger.warning(f"[bulk] Could not select or search mailbox '{mailbox}': {e}", exc_info=True)

            # Final ensure progress shows completed
            if progress_callback:
                try:
                    progress_callback(total, total)
                except Exception:
                    pass

            if not dataset:
                logger.warning("[bulk] Export produced an empty dataset")
            
            return dataset
    except Exception as e:
        logger.error(f"Bulk export failed: {e}", exc_info=True)
        return []

async def export_threads_dataset_bulk(
    user_uuid: UUID,
    identifiers: List[str],
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[Dict[str, Any]]:
    """
    Async wrapper for single-connection bulk export. The progress_callback, if provided,
    will be invoked from the worker thread.
    """
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    async with acquire_imap_slot(user_uuid):
        return await loop.run_in_executor(None, _export_threads_dataset_bulk_sync, identifiers, app_settings, progress_callback)
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
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import imap_connection, IMAPConnectionError, FolderResolver, FolderNotFoundError
from mcp_servers.imap_mcpserver.src.imap_client.helpers.body_parser import extract_body_formats
from uuid import UUID

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


# --- Async Wrappers ---

async def get_recent_inbox_message_ids(user_uuid: UUID, count: int = 20) -> List[str]:
    """Asynchronously gets recent Message-IDs from INBOX"""
    app_settings = load_app_settings(user_uuid=user_uuid)
    return await asyncio.to_thread(_get_recent_message_ids_sync, app_settings, count)

async def get_message_by_id(user_uuid: UUID, message_id: str) -> Optional[EmailMessage]:
    """
    Asynchronously gets a single EmailMessage by its Message-ID.
    """
    app_settings = load_app_settings(user_uuid=user_uuid)
    return await asyncio.to_thread(_get_message_by_id_sync, message_id, app_settings)

async def get_complete_thread(user_uuid: UUID, source_message: EmailMessage) -> Optional[EmailThread]:
    if not source_message or not source_message.message_id:
        return None
    app_settings = load_app_settings(user_uuid=user_uuid)
    return await asyncio.to_thread(_get_complete_thread_sync, source_message.message_id, app_settings)

async def get_recent_inbox_messages(user_uuid: UUID, count: int = 10) -> List[EmailMessage]:
    """Asynchronously gets the most recent messages from the inbox."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    return await asyncio.to_thread(_get_recent_messages_from_attribute_sync, '\\Inbox', app_settings, count)

async def get_recent_sent_messages(user_uuid: UUID, count: int = 20) -> List[EmailMessage]:
    """Asynchronously gets the most recent messages from the sent folder."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    return await asyncio.to_thread(_get_recent_messages_from_attribute_sync, '\\Sent', app_settings, count)

async def draft_reply(user_uuid: UUID, original_message: EmailMessage, reply_body: str) -> Dict[str, Any]:
    app_settings = load_app_settings(user_uuid=user_uuid)
    return await asyncio.to_thread(_draft_reply_sync, original_message, reply_body, app_settings)

async def set_label(user_uuid: UUID, message_id: str, label: str) -> Dict[str, Any]:
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _set_label_sync, message_id, label, app_settings)

async def get_emails(user_uuid: UUID, folder_name: str, count: int = 10, filter_by_labels: Optional[List[str]] = None) -> List[EmailMessage]:
    """Asynchronous wrapper for getting emails from a folder with optional label filtering."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
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
    with imap_connection(app_settings=app_settings) as (mail, resolver):
        # We don't need the resolver here, but the connection manager provides it.
        return await loop.run_in_executor(None, _get_all_folders_sync, mail)

async def get_all_labels(user_uuid: UUID) -> List[str]:
    """Asynchronously gets all labels from the IMAP server."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    try:
        with imap_connection(app_settings=app_settings) as (mail, resolver):
            return await asyncio.to_thread(_get_all_labels_sync, mail, resolver)
    except Exception as e:
        logger.error(f"Error getting all labels: {e}")
        return []

async def get_all_special_use_folders(user_uuid: UUID) -> List[str]:
    """
    Asynchronous wrapper to get a list of all special-use folder names.
    """
    app_settings = load_app_settings(user_uuid=user_uuid)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_all_special_use_folders_sync, app_settings)


async def get_messages_from_folder(user_uuid: UUID, folder_name: str, count: int = 10) -> List[EmailMessage]:
    """Asynchronously gets recent messages from a specific folder/label."""
    app_settings = load_app_settings(user_uuid=user_uuid)
    return await asyncio.to_thread(_get_messages_from_folder_sync, folder_name, count, app_settings)

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
    return await fetch_recent_threads_bulk(
        target_thread_count=target_thread_count,
        max_age_months=max_age_months,
        source_folder_attribute=source_folder_attribute,
        user_uuid=user_uuid
    )
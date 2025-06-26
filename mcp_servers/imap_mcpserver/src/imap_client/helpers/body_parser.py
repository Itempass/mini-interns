"""
Helper functions for parsing email bodies.

This module provides shared utilities for extracting and converting
email content from raw formats (HTML, plain text) into structured,
clean formats like markdown. This ensures consistent processing
across different parts of the application.
"""

import re
import logging
from typing import Dict
from email_reply_parser import EmailReplyParser
from bs4 import BeautifulSoup

try:
    import html2text
except ImportError:
    html2text = None

logger = logging.getLogger(__name__)

def extract_reply_from_html(html_body: str) -> str:
    """
    Extracts the reply portion from an HTML email body using BeautifulSoup
    to find and remove quoted content from various email clients like
    Outlook, Gmail, and Apple Mail.
    """
    if not html_body:
        return ""

    soup = BeautifulSoup(html_body, 'html.parser')

    # Strategy 1: Find Outlook's specific <hr> separator
    # This is a reliable marker used by some versions of Outlook.
    hr_marker = soup.find('hr', id='stopSpelling')
    if hr_marker:
        # When this marker is found, we remove it and everything that comes after it.
        for element in hr_marker.find_all_next():
            element.decompose()
        hr_marker.decompose()
        return str(soup).strip()

    # Strategy 2: Find Gmail's quote container
    # This preserves the original logic but uses a proper HTML parser.
    gmail_quote = soup.find('div', class_='gmail_quote')
    if gmail_quote:
        # Gmail often adds an attribution line (e.g., "On... wrote:") just
        # before the quote div. We can try to remove that too.
        attr_div = gmail_quote.find_previous_sibling('div', class_='gmail_attr')
        if attr_div:
            attr_div.decompose()
        gmail_quote.decompose()
        return str(soup).strip()

    # Strategy 3: Find generic blockquotes that look like replies
    # This targets Apple Mail's `type="cite"` and the common "On... wrote:" pattern.
    for blockquote in soup.find_all('blockquote'):
        # Check for Apple Mail's `type="cite"`
        if blockquote.get('type') == 'cite':
            blockquote.decompose()
            return str(soup).strip()
        
        # Check for the common "On [date], [person] wrote:" pattern
        # inside the blockquote, which is a strong signal of a quoted reply.
        if re.search(r'On\s.*(wrote|écrit):', blockquote.get_text(), re.IGNORECASE):
            blockquote.decompose()
            return str(soup).strip()

    # If no specific quote markers are found, we return the original content
    # to avoid accidentally removing parts of a valid email.
    return str(soup)


def extract_body_formats(msg) -> Dict[str, str]:
    """Extract body in multiple formats: raw, markdown, and cleaned"""
    html_body = ""
    text_body = ""

    # Extract both HTML and plain text if available
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            charset = part.get_content_charset() or 'utf-8'

            if content_type == "text/plain" and not text_body:
                try:
                    text_body = part.get_payload(decode=True).decode(charset, errors='ignore')
                except (UnicodeDecodeError, AttributeError):
                    text_body = str(part.get_payload())
            elif content_type == "text/html" and not html_body:
                try:
                    html_body = part.get_payload(decode=True).decode(charset, errors='ignore')
                except (UnicodeDecodeError, AttributeError):
                    html_body = str(part.get_payload())
    else:
        charset = msg.get_content_charset() or 'utf-8'
        content = msg.get_payload(decode=True)
        if isinstance(content, bytes):
            try:
                content = content.decode(charset, errors='ignore')
            except (UnicodeDecodeError, AttributeError):
                content = str(content)

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
        raw_body = extract_reply_from_html(html_body)
    else:
        raw_body = reply_text if reply_text else text_body

    # Convert HTML to markdown if we have HTML
    markdown_body = ""
    if html_body and html2text:
        try:
            # Extract only the reply part from Gmail HTML before converting to markdown
            reply_html = extract_reply_from_html(html_body)

            h = html2text.HTML2Text()
            h.ignore_links = False
            h.body_width = 0  # Don't wrap lines
            markdown_body = h.handle(reply_html).strip()
        except Exception as e:
            logger.warning(f"Error converting HTML to markdown: {e}")
            markdown_body = reply_text if reply_text else (text_body if text_body else html_body)
    else:
        # No HTML or no html2text library, use plain text
        markdown_body = reply_text if reply_text else (text_body if text_body else html_body)

    # Create cleaned version from the reply text
    cleaned_body = ""
    if reply_text:
        # Remove markdown-like formatting for a super clean version
        temp_cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', reply_text) # Links
        temp_cleaned = re.sub(r'(\*\*|__)(.*?)\1', r'\2', temp_cleaned)     # Bold
        temp_cleaned = re.sub(r'(\*|_)(.*?)\1', r'\2', temp_cleaned)       # Italics
        temp_cleaned = re.sub(r'#+\s', '', temp_cleaned)                  # Headers
        temp_cleaned = re.sub(r'`(.*?)`', r'\1', temp_cleaned)             # Code
        # Normalize whitespace
        cleaned_body = ' '.join(temp_cleaned.split())

    return {
        'raw': raw_body or "",
        'markdown': markdown_body or "",
        'cleaned': cleaned_body or ""
    } 
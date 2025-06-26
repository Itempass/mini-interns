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

try:
    import html2text
except ImportError:
    html2text = None

logger = logging.getLogger(__name__)

def extract_reply_from_gmail_html(html_body: str) -> str:
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
        raw_body = extract_reply_from_gmail_html(html_body)
    else:
        raw_body = reply_text if reply_text else text_body

    # Convert HTML to markdown if we have HTML
    markdown_body = ""
    if html_body and html2text:
        try:
            # Extract only the reply part from Gmail HTML before converting to markdown
            reply_html = extract_reply_from_gmail_html(html_body)

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
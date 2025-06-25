"""
Text utilities for cleaning and formatting email content.
"""
import re


def clean_email_text_for_storage(text: str) -> str:
    """
    Clean email text for storage and vector search processing.
    Removes formatting artifacts while preserving readability.
    
    Args:
        text: Raw email text with potential \r\n, \n, and other formatting
        
    Returns:
        Cleaned text suitable for storage and embedding
    """
    if not text:
        return ""
    
    # Replace all types of line breaks with spaces
    cleaned = text.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
    
    # Remove excessive whitespace (multiple spaces, tabs)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Clean up common email artifacts
    cleaned = re.sub(r'\[image:.*?\]', '', cleaned)  # Remove image references
    cleaned = re.sub(r'\[image\]', '', cleaned)  # Remove simple image tags
    
    # Clean up excessive punctuation repetition
    cleaned = re.sub(r'>{2,}', '>', cleaned)  # Multiple > to single >
    
    # Trim and return
    return cleaned.strip()


def format_email_for_display(subject: str, from_addr: str, to_addr: str, 
                           cc_addr: str, date: str, body: str) -> str:
    """
    Format email for clean display in thread results.
    
    Args:
        subject: Email subject
        from_addr: From address
        to_addr: To address  
        cc_addr: CC address
        date: Date string
        body: Email body text
        
    Returns:
        Cleanly formatted email string
    """
    # Clean the body text
    clean_body = clean_email_text_for_storage(body)
    
    # Build the formatted output
    lines = [
        f"Subject: {subject}",
        f"from: {from_addr}",
        f"to: {to_addr or 'N/A'}",
    ]
    
    if cc_addr:
        lines.append(f"cc: {cc_addr}")
    
    lines.extend([
        f"date: {date}",
        clean_body
    ])
    
    return " ".join(lines)


def format_thread_separator() -> str:
    """
    Returns a clean separator between emails in a thread.
    """
    return "\n\n---NEXT EMAIL IN THREAD---\n\n" 
"""
Utilities for handling contextual IDs.

A contextual ID is a string that combines a mailbox name and a UID,
allowing for unambiguous identification of an email across different folders.
"""
import base64
from typing import Tuple

def create_contextual_id(mailbox: str, uid: str) -> str:
    """Creates a contextual ID from a mailbox and a UID."""
    encoded_mailbox = base64.b64encode(mailbox.encode('utf-8')).decode('utf-8')
    return f"{encoded_mailbox}:{uid}"

def parse_contextual_id(contextual_id: str) -> Tuple[str, str]:
    """
    Parses a contextual ID into a mailbox and a UID.

    If parsing fails, it assumes the ID is a simple UID from the 'inbox'.
    """
    try:
        encoded_mailbox, uid = contextual_id.split(':', 1)
        decoded_mailbox = base64.b64decode(encoded_mailbox.encode('utf-8')).decode('utf-8')
        return decoded_mailbox, uid
    except (ValueError, TypeError, base64.binascii.Error):
        return 'inbox', contextual_id

def is_valid_contextual_id(contextual_id: str) -> bool:
    """
    Validates if the given ID is a valid contextual ID.
    A valid contextual ID is a base64 encoded mailbox name, followed by a colon, followed by a UID.
    Example: SU5CT1g=:5836
    """
    if not isinstance(contextual_id, str):
        return False
    parts = contextual_id.split(':', 1)
    if len(parts) != 2:
        return False
    
    encoded_mailbox, uid = parts
    if not uid.isdigit():
        return False

    try:
        base64.b64decode(encoded_mailbox.encode('utf-8'), validate=True)
    except (base64.binascii.Error, ValueError):
        return False

    return True 
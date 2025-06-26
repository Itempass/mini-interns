"""
Helper functions for contextual ID management.
"""
import base64

def create_contextual_id(mailbox: str, uid: str) -> str:
    """Creates a contextual ID from a mailbox and a UID."""
    encoded_mailbox = base64.b64encode(mailbox.encode('utf-8')).decode('utf-8')
    return f"{encoded_mailbox}:{uid}" 
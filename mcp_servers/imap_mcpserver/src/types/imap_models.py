"""
Pydantic models for IMAP operations.
"""
from pydantic import BaseModel
from email.message import Message
from typing import Any

class RawEmail(BaseModel):
    """
    Represents a raw email fetched from the IMAP server.
    """
    uid: str
    msg: Any # email.message.Message is not directly pydantic compatible

    class Config:
        arbitrary_types_allowed = True 
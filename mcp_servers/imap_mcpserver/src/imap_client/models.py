from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class EmailMessage(BaseModel):
    """Individual email message in a thread"""
    uid: str  # Contextual ID (base64_mailbox:uid)
    message_id: str
    from_: str = Field(alias='from')  # 'from' is a Python keyword
    to: str
    cc: Optional[str] = ""
    bcc: Optional[str] = ""
    subject: str
    date: str
    body_raw: str  # Raw body (HTML or plain text)
    body_markdown: str  # Converted to markdown format
    body_cleaned: str  # Clean text only, no line breaks or formatting
    gmail_labels: List[str] = Field(default_factory=list)  # Folder information
    references: Optional[str] = ""
    in_reply_to: Optional[str] = ""
    
    model_config = {"populate_by_name": True}  # Allow using 'from' field name

class EmailThread(BaseModel):
    """Complete email thread with all messages"""
    thread_id: str  # Gmail thread ID (always available via X-GM-THRID)
    message_count: int
    messages: List[EmailMessage]
    participants: List[str] = Field(default_factory=list)  # Unique email addresses involved
    subject: str  # Subject of the thread (from first message)
    last_message_date: str
    folders: List[str] = Field(default_factory=list)  # All folders this thread appears in
    
    @classmethod
    def from_messages(cls, messages: List[EmailMessage], thread_id: str) -> 'EmailThread':
        """Create an EmailThread from a list of EmailMessage objects"""
        if not messages:
            raise ValueError("Cannot create thread from empty message list")
        
        # Sort messages by date
        sorted_messages = sorted(messages, key=lambda m: m.date)
        
        # Extract participants (unique email addresses)
        participants = set()
        all_folders = set()
        
        for msg in messages:
            # Extract email addresses from From, To, CC fields
            if msg.from_:
                participants.add(msg.from_.split('<')[-1].strip('>') if '<' in msg.from_ else msg.from_)
            if msg.to:
                for email in msg.to.split(','):
                    participants.add(email.strip().split('<')[-1].strip('>') if '<' in email else email.strip())
            if msg.cc:
                for email in msg.cc.split(','):
                    participants.add(email.strip().split('<')[-1].strip('>') if '<' in email else email.strip())
            
            # Collect all folders
            all_folders.update(msg.gmail_labels)
        
        return cls(
            thread_id=thread_id,
            message_count=len(messages),
            messages=sorted_messages,
            participants=list(participants),
            subject=sorted_messages[0].subject,
            last_message_date=sorted_messages[-1].date,
            folders=list(all_folders)
        )
    
    @property
    def markdown(self) -> str:
        """Format the entire thread as markdown"""
        lines = []
        lines.append("# Email Thread")
        lines.append("")
        
        for i, message in enumerate(self.messages, 1):
            lines.append(f"## Message {i}:")
            lines.append("")
            lines.append(f"* **From:** {message.from_}")
            lines.append(f"* **To:** {message.to}")
            if message.cc:
                lines.append(f"* **CC:** {message.cc}")
            lines.append(f"* **Date:** {message.date}")
            lines.append(f"* **Message ID:** {message.message_id}")
            lines.append(f"* **Subject:** {message.subject}")
            lines.append("")
            lines.append(message.body_markdown)
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)

 
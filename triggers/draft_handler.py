import logging
import re
import imaplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import email.utils
from datetime import datetime
from shared.app_settings import load_app_settings

logger = logging.getLogger(__name__)

def markdown_to_html(markdown_text: str) -> str:
    """
    Convert markdown formatting to HTML.
    Supports basic markdown features like the example.
    """
    html = markdown_text
    
    # Bold text (**text** or __text__) - process first to avoid conflicts
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__(.*?)__', r'<strong>\1</strong>', html)
    
    # Italic text (*text* or _text_) - process after bold to avoid conflicts
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

def find_drafts_folder(mail) -> str:
    """
    Find the correct drafts folder name by trying common variations.
    Uses imaplib like the example.
    """
    draft_folders = [
        "[Gmail]/Drafts",
        "DRAFTS", 
        "Drafts",
        "[Google Mail]/Drafts",
    ]
    selected_folder = None
    
    try:
        # List all folders to find the correct drafts folder
        status, folders = mail.list()
        if status == "OK":
            folder_list = []
            for folder in folders:
                folder_name = (
                    folder.decode().split('"')[-2]
                    if '"' in folder.decode()
                    else folder.decode().split()[-1]
                )
                folder_list.append(folder_name)

            logger.info(f"Available folders: {folder_list}")

            # Find the drafts folder
            for draft_folder in draft_folders:
                if draft_folder in folder_list:
                    selected_folder = draft_folder
                    logger.info(f"Found drafts folder: {selected_folder}")
                    break

            # If we couldn't find a standard drafts folder, look for any folder containing "draft"
            if not selected_folder:
                for folder_name in folder_list:
                    if "draft" in folder_name.lower():
                        selected_folder = folder_name
                        logger.info(f"Found drafts folder by search: {selected_folder}")
                        break
                        
    except Exception as e:
        logger.warning(f"Error listing folders: {e}")
    
    if not selected_folder:
        # Default to [Gmail]/Drafts if we can't find it
        selected_folder = "[Gmail]/Drafts"
        logger.info(f"Using default drafts folder: {selected_folder}")
        
    return selected_folder

def create_draft_reply(original_msg, draft_content: str) -> dict:
    """
    Create a draft reply to an existing email and save it to the drafts folder.
    Following the example implementation exactly using imaplib.
    
    Args:
        original_msg: The original email message object from imap_tools
        draft_content: The draft reply content (supports markdown)
    
    Returns:
        Dict with success status and message
    """
    try:
        app_settings = load_app_settings()
        
        if not all([app_settings.IMAP_SERVER, app_settings.IMAP_USERNAME, app_settings.IMAP_PASSWORD]):
            return {
                "success": False,
                "message": "IMAP settings not fully configured"
            }
        
        if len(draft_content) < 5:
            return {
                "success": False,
                "message": "Reply body is too short. Please provide a complete message."
            }
        
        logger.info("Creating draft reply...")
        logger.info(f"Original email from: {original_msg.from_}")
        logger.info(f"Original subject: {original_msg.subject}")
        
        # Prepare reply subject
        original_subject = original_msg.subject or "(No Subject)"
        reply_subject = original_subject
        if not reply_subject.lower().startswith("re:"):
            reply_subject = f"Re: {reply_subject}"
        
        # Connect to Gmail IMAP server with SSL on port 993 (exactly like example)
        mail = imaplib.IMAP4_SSL(app_settings.IMAP_SERVER, 993)
        logger.info(f"Authenticating with {app_settings.IMAP_SERVER}")
        mail.login(app_settings.IMAP_USERNAME, app_settings.IMAP_PASSWORD)
        
        # Create the reply message
        reply_message = MIMEMultipart("alternative")
        reply_message["Subject"] = reply_subject
        reply_message["From"] = app_settings.IMAP_USERNAME
        reply_message["To"] = original_msg.from_
        reply_message["Date"] = email.utils.formatdate(localtime=True)
        
        # Add threading headers for proper email threading
        if hasattr(original_msg, 'message_id') and original_msg.message_id:
            reply_message["In-Reply-To"] = original_msg.message_id
            reply_message["References"] = original_msg.message_id
        
        # Create both plain text and HTML versions
        part1 = MIMEText(draft_content, "plain")
        part2 = MIMEText(markdown_to_html(draft_content), "html")
        reply_message.attach(part1)
        reply_message.attach(part2)
        
        # Find the correct drafts folder
        drafts_folder = find_drafts_folder(mail)
        
        logger.info(f"Saving draft reply to folder: {drafts_folder}")
        
        # Convert message to string and append to drafts folder (exactly like example)
        message_string = reply_message.as_string()
        
        # Append the message to the drafts folder
        result = mail.append(
            drafts_folder, None, None, message_string.encode("utf-8")
        )
        
        mail.logout()
        
        if result[0] == "OK":
            result_message = f"""✓ DRAFT_REPLY_CREATED ✓
TO: {original_msg.from_}
SUBJECT: {reply_subject}
FOLDER: {drafts_folder}

DRAFT CONTENT:
{draft_content}

Draft reply has been saved to {drafts_folder} folder and can be accessed through your email client."""
            
            logger.info("Draft reply created successfully")
            logger.info(f"Saved to folder: {drafts_folder}")
            
            return {
                "success": True,
                "message": result_message,
                "details": {
                    "to": original_msg.from_,
                    "subject": reply_subject,
                    "folder": drafts_folder
                }
            }
        else:
            error_msg = f"Error creating draft reply: {result[1][0].decode() if result[1] else 'Unknown error'}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
            
    except Exception as e:
        error_msg = f"Error creating draft reply: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "message": error_msg
        } 
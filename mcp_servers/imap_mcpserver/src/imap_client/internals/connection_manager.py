"""
Thread-safe IMAP connection manager for email operations.

This module provides a robust connection management system that ensures
thread safety and proper resource cleanup for IMAP operations.
"""

import contextlib
import imaplib
import logging
import re
from typing import Generator, Optional, Dict, List, Tuple
from shared.app_settings import load_app_settings

logger = logging.getLogger(__name__)

class FolderNotFoundError(Exception):
    """Raised when a required special-use folder cannot be found."""
    pass

class FolderResolver:
    """
    Discovers and provides language-agnostic names for special-use mailboxes.
    Uses RFC 6154 "SPECIAL-USE" attributes and falls back to guessing.
    An instance of this class is tied to a single IMAP connection.
    """
    SPECIAL_USE_ATTRIBUTES = {'\\All', '\\Drafts', '\\Sent', '\\Junk', '\\Trash'}
    FALLBACK_MAP = {
        '\\Sent': ('Sent', '[Gmail]/Sent Mail', 'Sent Items'),
        '\\Drafts': ('Drafts', '[Gmail]/Drafts'),
        '\\All': ('All Mail', '[Gmail]/All Mail'),
        '\\Trash': ('Trash', '[Gmail]/Trash', 'Deleted Items'),
        '\\Junk': ('Junk', 'Spam'),
        '\\Inbox': ('INBOX',) # Inbox is a special case
    }

    def __init__(self, mail: imaplib.IMAP4_SSL):
        self._mail = mail
        self._folder_map: Dict[str, str] = {}
        self._raw_folder_list: List[str] = []
        self._discover_folders()

    def _discover_folders(self):
        """
        Calls LIST to get all folders, their attributes, and names.
        Populates the internal map of special-use attributes to real folder names.
        """
        try:
            status, folders = self._mail.list()
            if status != 'OK':
                return

            self._raw_folder_list = [f.decode() for f in folders if isinstance(f, bytes)]
            
            for folder_data in self._raw_folder_list:
                match = re.search(r'\((?P<attributes>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)', folder_data)
                if not match:
                    continue

                attributes = match.group('attributes').split()
                name = match.group('name').strip('"')

                for attr in attributes:
                    if attr in self.SPECIAL_USE_ATTRIBUTES:
                        self._folder_map[attr] = name
                        logger.info(f"Found special-use folder: {attr} -> {name}")
        except Exception as e:
            logger.error(f"Error discovering folders: {e}")

    def get_folder_by_attribute(self, attribute: str) -> str:
        """
        Returns the real folder name for a given special-use attribute.
        If not found via SPECIAL-USE, it uses fallback logic.
        
        Raises:
            FolderNotFoundError: If the folder cannot be resolved after all fallbacks.
        """
        # 1. Check the discovered map first
        if attribute in self._folder_map:
            return self._folder_map[attribute]
        
        # Handle INBOX as a special case
        if attribute == '\\Inbox':
            return 'INBOX'

        # 2. If not found, try fallback logic
        logger.warning(f"Could not find special-use folder '{attribute}'. Trying fallbacks.")
        fallback_names = self.FALLBACK_MAP.get(attribute, [])
        
        all_folder_names = []
        for folder_data in self._raw_folder_list:
             match = re.search(r'"(.*?)"$', folder_data)
             if match:
                 all_folder_names.append(match.group(1))

        # Check for exact matches from our fallback list
        for name in fallback_names:
            if name in all_folder_names:
                logger.info(f"Found fallback folder for {attribute}: {name}")
                return name
        
        # Check for substring matches as a last resort
        search_term = attribute.strip('\\').lower()
        for folder_name in all_folder_names:
            if search_term in folder_name.lower():
                logger.info(f"Found fallback folder for {attribute} by search: {folder_name}")
                return folder_name

        error_msg = f"Could not resolve folder for attribute '{attribute}' after all fallbacks."
        logger.error(error_msg)
        raise FolderNotFoundError(error_msg)

class IMAPConnectionError(Exception):
    """Custom exception for IMAP connection issues."""
    pass

class IMAPConnectionManager:
    """
    Thread-safe IMAP connection manager.
    
    Each context manager call creates a new, isolated connection to ensure
    thread safety. Connections are automatically cleaned up on exit.
    """
    
    def __init__(self, 
                 server: Optional[str] = None,
                 username: Optional[str] = None, 
                 password: Optional[str] = None,
                 port: int = 993):
        """
        Initialize connection manager with IMAP settings.
        
        Args:
            server: IMAP server hostname (defaults to app settings or "imap.gmail.com")
            username: IMAP username (defaults to app settings)
            password: IMAP password (defaults to app settings)
            port: IMAP port (defaults to 993)
        """
        # Only load settings from app_settings if any parameters are missing
        if not server or not username or not password:
            settings = load_app_settings()
            self.server = server or settings.IMAP_SERVER
            self.username = username or settings.IMAP_USERNAME
            self.password = password or settings.IMAP_PASSWORD
        else:
            # All parameters provided, use them directly
            self.server = server
            self.username = username
            self.password = password
        self.port = port
        
        # Validate required settings
        if not self.username or not self.password:
            raise ValueError("IMAP username and password must be provided via parameters or app settings")

    @contextlib.contextmanager
    def connect(self) -> Generator[Tuple[imaplib.IMAP4_SSL, FolderResolver], None, None]:
        """
        Create a new IMAP connection with guaranteed cleanup.
        
        Yields:
            A tuple containing:
            - imaplib.IMAP4_SSL: Connected and authenticated IMAP client
            - FolderResolver: An instance to resolve special-use folder names
            
        Raises:
            IMAPConnectionError: If connection or authentication fails
        """
        mail = None
        try:
            logger.debug(f"Connecting to IMAP server: {self.server}:{self.port}")
            mail = imaplib.IMAP4_SSL(self.server, self.port)
            mail.login(self.username, self.password)
            logger.debug("IMAP login successful")
            
            # Create a resolver for this connection
            resolver = FolderResolver(mail)
            
            yield mail, resolver
            
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP connection/authentication failed: {e}")
            raise IMAPConnectionError(f"Failed to connect to IMAP server: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during IMAP connection: {e}")
            raise IMAPConnectionError(f"Unexpected IMAP error: {e}") from e
        finally:
            if mail:
                try:
                    mail.logout()
                    logger.debug("IMAP logout successful")
                except Exception as e:
                    logger.warning(f"Error during IMAP logout (connection may already be closed): {e}")

# No longer using a singleton for the default manager to ensure settings are always fresh.
def get_default_connection_manager() -> IMAPConnectionManager:
    """
    Get a new connection manager instance.
    
    This ensures that the latest application settings are loaded each time
    a connection is requested, allowing for dynamic updates without restarting
    the service.
    """
    return IMAPConnectionManager()

@contextlib.contextmanager
def imap_connection() -> Generator[Tuple[imaplib.IMAP4_SSL, FolderResolver], None, None]:
    """
    Convenience function for getting an IMAP connection using default settings.
    
    This is equivalent to get_default_connection_manager().connect() but shorter.
    
    Example:
        with imap_connection() as (mail, resolver):
            sent_folder = resolver.get_folder_by_attribute('\\Sent')
            mail.select(sent_folder)
            # ... do IMAP operations
    """
    with get_default_connection_manager().connect() as (mail, resolver):
        yield mail, resolver 
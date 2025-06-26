"""
Thread-safe IMAP connection manager for email operations.

This module provides a robust connection management system that ensures
thread safety and proper resource cleanup for IMAP operations.
"""

import contextlib
import imaplib
import logging
from typing import Generator, Optional
from shared.app_settings import load_app_settings

logger = logging.getLogger(__name__)

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
    def connect(self) -> Generator[imaplib.IMAP4_SSL, None, None]:
        """
        Create a new IMAP connection with guaranteed cleanup.
        
        Yields:
            imaplib.IMAP4_SSL: Connected and authenticated IMAP client
            
        Raises:
            IMAPConnectionError: If connection or authentication fails
        """
        mail = None
        try:
            logger.debug(f"Connecting to IMAP server: {self.server}:{self.port}")
            mail = imaplib.IMAP4_SSL(self.server, self.port)
            mail.login(self.username, self.password)
            logger.debug("IMAP login successful")
            yield mail
            
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

# Global connection manager instance
_default_manager = None

def get_default_connection_manager() -> IMAPConnectionManager:
    """Get the default global connection manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = IMAPConnectionManager()
    return _default_manager

@contextlib.contextmanager
def imap_connection() -> Generator[imaplib.IMAP4_SSL, None, None]:
    """
    Convenience function for getting an IMAP connection using default settings.
    
    This is equivalent to get_default_connection_manager().connect() but shorter.
    
    Example:
        with imap_connection() as mail:
            mail.select('INBOX')
            # ... do IMAP operations
    """
    with get_default_connection_manager().connect() as mail:
        yield mail 
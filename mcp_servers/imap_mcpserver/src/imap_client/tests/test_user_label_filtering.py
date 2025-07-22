import os
import asyncio
import logging
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv
import unittest
import sys
import re

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
sys.path.insert(0, project_root)

from mcp_servers.imap_mcpserver.src.imap_client.client import _get_complete_thread_sync, _find_uid_by_message_id
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import IMAPConnectionManager

load_dotenv(override=True)

# Setup logging
logging.basicConfig(level=logging.INFO) # Changed to INFO to reduce noise, can be set to DEBUG if needed
logger = logging.getLogger(__name__)

class TestUserLabelFiltering(unittest.TestCase):
    
    def setUp(self):
        """Check for required environment variables before running tests."""
        required_vars = ["TEST_IMAP_USER", "TEST_IMAP_PASSWORD", "TEST_IMAP_SERVER"]
        if not all(os.getenv(var) for var in required_vars):
            self.skipTest("Missing required test IMAP credentials in .env file.")
            
        self.test_conn_manager = IMAPConnectionManager(
            server=os.environ["TEST_IMAP_SERVER"],
            username=os.environ["TEST_IMAP_USER"],
            password=os.environ["TEST_IMAP_PASSWORD"],
        )

    def test_label_parsing_handles_all_formats(self):
        """
        Tests that the label parsing logic correctly handles various formats:
        - Unquoted labels without spaces (e.g., github)
        - Quoted labels with spaces (e.g., "cold outreach")
        - A mix of both in the same thread.
        """
        test_cases = [
            ("GitHub Notification", "Itempass/mini-interns/check-suites/CS_kwDOO-DVcs8AAAAJjsie5A/1751447376@github.com", ["github"]),
            ("Label with Space", "94017778-ba99-4c4c-9842-05771ce8a3e7@10studiobase.com", ["cold outreach"]),
            ("Another Label with Space", "CAJsvGQYGogsAUdwaDGCN1C4Dy_yHQHjOkizBdwsQ2KiOa+DGbA@mail.gmail.com", ["test emails"])
        ]
        
        for name, message_id, expected_labels in test_cases:
            with self.subTest(msg=f"Testing case: {name}"):
                with patch('mcp_servers.imap_mcpserver.src.imap_client.client.imap_connection', self.test_conn_manager.connect):
                    email_thread = _get_complete_thread_sync(message_id)

                self.assertIsNotNone(email_thread, f"Failed to retrieve thread for '{name}'")
                
                # Check that the expected labels are present in the final user labels.
                # We use a set for comparison to ignore order.
                self.assertSetEqual(set(email_thread.most_recent_user_labels), set(expected_labels),
                                    f"Incorrect labels for '{name}'. Found: {email_thread.most_recent_user_labels}")

if __name__ == "__main__":
    unittest.main() 
import unittest
from unittest.mock import patch, MagicMock
from ...src.services.imap_service import IMAPService

class TestSignatureDetection(unittest.TestCase):

    def setUp(self):
        """Set up test data for signature detection."""
        self.mock_email_bodies = [
            # Email 1: Simple signature
            {
                'text': "Hello team,\n\nPlease find the attached report.\n\nBest,\nJohn Doe",
                'html': "<html><body><p>Hello team,</p><p>Please find the attached report.</p><div>Best,<br/>John Doe</div></body></html>"
            },
            # Email 2: More complex signature with a div
            {
                'text': "Hi everyone,\n\nHere is the weekly update.\n\nBest,\nJohn Doe",
                'html': "<html><body><p>Hi everyone,</p><p>Here is the weekly update.</p><div>Best,<br/>John Doe</div></body></html>"
            },
            # Email 3: Signature wrapped in multiple tags
            {
                'text': "Team,\n\nMeeting notes are now available.\n\nBest,\nJohn Doe",
                'html': "<html><body><p>Team,</p><p>Meeting notes are now available.</p><div><div>Best,<br/>John Doe</div></div></body></html>"
            },
            # Email 4: No signature
            {
                'text': "Just a quick question.",
                'html': "<html><body><p>Just a quick question.</p></body></html>"
            }
        ]

    def test_find_best_signature_scenario_1(self):
        """Test the _find_best_signature method with a clear signature pattern."""
        # Arrange
        # For this test, we'll assume a consistent signature across multiple emails
        consistent_emails = self.mock_email_bodies[:3]
        
        # Act
        plain_signature, html_signature = IMAPService._find_best_signature(consistent_emails)

        # Assert
        expected_plain_signature = "Best,\nJohn Doe"
        expected_html_signature = "<div>Best,<br/>John Doe</div>"
        
        self.assertEqual(expected_plain_signature, plain_signature)
        self.assertEqual(expected_html_signature, html_signature)

if __name__ == '__main__':
    unittest.main() 
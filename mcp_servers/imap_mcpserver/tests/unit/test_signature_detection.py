import unittest
import logging
import email
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from mcp_servers.imap_mcpserver.src.imap_client.client import _get_user_signature

logging.basicConfig(level=logging.INFO)

class TestGmailSignatureDetection(unittest.TestCase):

    def setUp(self):
        """Set up test data for Gmail signature detection."""
        # Create mock email messages with the specific Gmail signature to test
        self.gmail_signature_html = (
            '<div dir="ltr"><div><br clear="all"></div><div><div dir="ltr" class="gmail_signature" data-smartmail="gmail_signature">'
            '<div dir="ltr"><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            '<b>Hendrik Cornelissen</b></div><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            'Investment Team</div><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            '<img width="96" height="26" src="https://ci3.googleusercontent.com/mail-sig/AIorK4xjFn52Uh1ifuwHckybOagKzKw1o-CPvFd8yQHPD7wOagh30jOfIjUxzJmMG2DSaOl88CpXuH-12QGL"><br></div>'
            '<div style="line-height:1.5"><span style="color:rgb(68,68,68);font-family:sans-serif;font-size:12px">'
            'Cell: +1 650 495-6150</span></div><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            '<a href="https://www.plugandplaytechcenter.com/" rel="noopener" style="color:rgb(17,85,204)" target="_blank">'
            'plugandplaytechcenter.com</a></div></div></div></div></div>'
        )
        
        # Expected extracted signature (just the gmail_signature div contents)
        self.expected_extracted_signature = (
            '<div class="gmail_signature" data-smartmail="gmail_signature" dir="ltr">'
            '<div dir="ltr"><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            '<b>Hendrik Cornelissen</b></div><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            'Investment Team</div><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            '<img height="26" src="https://ci3.googleusercontent.com/mail-sig/AIorK4xjFn52Uh1ifuwHckybOagKzKw1o-CPvFd8yQHPD7wOagh30jOfIjUxzJmMG2DSaOl88CpXuH-12QGL" width="96"/><br/></div>'
            '<div style="line-height:1.5"><span style="color:rgb(68,68,68);font-family:sans-serif;font-size:12px">'
            'Cell: +1 650 495-6150</span></div><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            '<a href="https://www.plugandplaytechcenter.com/" rel="noopener" style="color:rgb(17,85,204)" target="_blank">'
            'plugandplaytechcenter.com</a></div></div></div>'
        )
        
        self.plain_signature = (
            "-- \n"
            "Hendrik Cornelissen\n"
            "Investment Team\n\n"
            "Cell: +1 650 495-6150\n"
            "plugandplaytechcenter.com"
        )

    def create_mock_email_bytes(self, plain_body: str, html_body: str) -> bytes:
        """Helper to create mock email message bytes."""
        msg = email.message.EmailMessage()
        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype='html')
        return msg.as_bytes()

    @patch('mcp_servers.imap_mcpserver.src.imap_client.client.imaplib.IMAP4_SSL')
    def test_gmail_signature_detection(self, mock_imap_ssl):
        """Test signature detection with a gmail signature."""
        # Arrange
        signature_plain = "Hendrik Cornelissen\nInvestment Team\n\nCell: +1 650 495-6150\nplugandplaytechcenter.com"

        mock_mail = MagicMock()
        mock_imap_ssl.return_value = mock_mail
        mock_mail.select.return_value = ('OK', None)
        mock_mail.uid.side_effect = [
            ('OK', [b'1 2 3']),  # search results
            ('OK', [(b'1 (RFC822 {123}', self.create_mock_email_bytes(
                f"Hello team,\n\nHere is the report.\n\n{signature_plain}",
                f'<html><body><p>Hello team,</p><p>Here is the report.</p>{self.gmail_signature_html}</body></html>'
            ))]),
            ('OK', [(b'2 (RFC822 {123}', self.create_mock_email_bytes(
                f"Hi,\n\nPlease review this document.\n\n{signature_plain}",
                f'<html><body><p>Hi,</p><p>Please review this document.</p>{self.gmail_signature_html}</body></html>'
            ))]),
            ('OK', [(b'3 (RFC822 {123}', self.create_mock_email_bytes(
                f"Team,\n\nFYI.\n\n{signature_plain}",
                f'<html><body><p>Team,</p><p>FYI.</p>{self.gmail_signature_html}</body></html>'
            ))])
        ]

        # Act
        plain_signature, html_signature = _get_user_signature()

        # Assert
        self.assertIsNotNone(html_signature)
        self.assertIn('gmail_signature', html_signature)
        self.assertIn('Hendrik Cornelissen', html_signature)
        self.assertIn('Investment Team', html_signature)
        
        # Check if plain signature was detected (it's OK if it's None for Gmail shortcut)
        if plain_signature:
            self.assertIn('Hendrik Cornelissen', plain_signature)
        
        # Normalize HTML comparison
        soup_expected = BeautifulSoup(self.expected_extracted_signature, 'lxml')
        soup_actual = BeautifulSoup(html_signature, 'lxml')
        self.assertEqual(str(soup_expected), str(soup_actual))

    @patch('mcp_servers.imap_mcpserver.src.imap_client.client.imaplib.IMAP4_SSL')
    def test_gmail_signature_detection_no_emails(self, mock_imap_ssl):
        """Test Gmail signature detection when no emails are found."""
        # Arrange
        mock_mail = MagicMock()
        mock_imap_ssl.return_value = mock_mail
        
        # Mock empty response
        mock_mail.select.return_value = ('OK', None)
        mock_mail.uid.return_value = ('OK', [b''])
        
        # Act
        plain_signature, html_signature = _get_user_signature()

        # Assert
        self.assertIsNone(plain_signature)
        self.assertIsNone(html_signature)

    @patch('mcp_servers.imap_mcpserver.src.imap_client.client.imaplib.IMAP4_SSL')
    def test_gmail_signature_detection_connection_failure(self, mock_imap_ssl):
        """Test Gmail signature detection when IMAP connection fails."""
        # Arrange
        mock_imap_ssl.side_effect = Exception("Connection failed")
        
        # Act
        plain_signature, html_signature = _get_user_signature()

        # Assert
        self.assertIsNone(plain_signature)
        self.assertIsNone(html_signature)

    @patch('mcp_servers.imap_mcpserver.src.imap_client.client.imaplib.IMAP4_SSL')
    def test_gmail_signature_detection_no_gmail_signature_class(self, mock_imap_ssl):
        """Test Gmail signature detection when emails don't have gmail_signature class."""
        # Arrange
        mock_mail = MagicMock()
        mock_imap_ssl.return_value = mock_mail
        
        # Mock responses with HTML but no gmail_signature class
        html_without_signature = '<html><body><p>Hello team,</p><p>Here is the report.</p><div>Regular footer</div></body></html>'
        
        mock_mail.select.return_value = ('OK', None)
        mock_mail.uid.side_effect = [
            ('OK', [b'1 2 3']),
            ('OK', [(b'1 (RFC822 {123}', self.create_mock_email_bytes(
                "Hello team,\n\nHere is the report.",
                html_without_signature
            ))]),
            ('OK', [(b'2 (RFC822 {123}', self.create_mock_email_bytes(
                "Hi,\n\nPlease review this document.",  
                html_without_signature
            ))]),
            ('OK', [(b'3 (RFC822 {123}', self.create_mock_email_bytes(
                "Team,\n\nFYI.",
                html_without_signature
            ))])
        ]
        
        # Act
        plain_signature, html_signature = _get_user_signature()

        # Assert
        self.assertIsNone(plain_signature)
        self.assertIsNone(html_signature)

if __name__ == '__main__':
    unittest.main() 
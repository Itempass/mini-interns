import unittest
import logging
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from ...src.services.imap_service import IMAPService

logging.basicConfig(level=logging.INFO)

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

    def test_find_best_signature_with_elaborate_signature(self):
        """Test signature detection with a more elaborate signature."""
        # Arrange
        signature_html = (
            '<div class="c x7 y9 w4 h4">'
            '<div class="t m0 x0 h2 yb ff1 fs0 fc2 sc0 ls8 ws0">--</div>'
            '<div class="t m0 x0 h2 yc ff1 fs0 fc2 sc0 ls9 ws0">Arthur</div>'
            '<div class="t m1 x0 h5 yd ff1 fs1 fc2 sc0 lsa ws0">Co-founder </div>'
            '<div class="t m0 x0 h2 ye ff1 fs0 fc3 sc0 lsb ws0"><a href="https://itempass.com">Itempass.com</a></div>'
            '<img class="bi x0 y0 w1 h0" alt="logo" src="logo.png"/>'
            '</div>'
        )
        signature_plain = "--\nArthur\nCo-founder \nItempass.com"

        elaborate_emails = [
            {
                'text': f"Hello team,\n\nHere is the report.\n\n{signature_plain}",
                'html': f'<html><body><p>Hello team,</p><p>Here is the report.</p>{signature_html}</body></html>'
            },
            {
                'text': f"Hi,\n\nPlease review this document.\n\n{signature_plain}",
                'html': f'<html><body><p>Hi,</p><p>Please review this document.</p>{signature_html}</body></html>'
            },
            {
                'text': f"Team,\n\nFYI.\n\n{signature_plain}",
                'html': f'<html><body><p>Team,</p><p>FYI.</p>{signature_html}</body></html>'
            }
        ]

        # Act
        plain_signature, html_signature = IMAPService._find_best_signature(elaborate_emails)

        # Assert
        expected_plain_signature = "--\nArthur\nCo-founder \nItempass.com"
        
        # Normalize HTML by parsing and re-serializing to handle attribute order differences
        soup_expected = BeautifulSoup(signature_html, 'lxml')
        soup_actual = BeautifulSoup(html_signature, 'lxml')

        self.assertEqual(expected_plain_signature, plain_signature)
        self.assertEqual(str(soup_expected), str(soup_actual))

    def test_find_best_signature_with_gmail_signature(self):
        """Test signature detection with a gmail signature."""
        # Arrange
        signature_html = (
            '<div dir="ltr"><div><br clear="all"></div><div><div dir="ltr" class="gmail_signature" data-smartmail="gmail_signature">'
            '<div dir="ltr"><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            '<b>Hendrik Cornelissen</b></div><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            'Investment Team</div><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            '<img width="96" height="26" src="https://ci3.googleusercontent.com/mail-sig/AIorK4xjFn52Uh1ifuwHckybOagKzKw1o-CPvFd8yQHPD7wOagh30jOfIjUxzJmMG2DSaOl88CpXuH-12QGL"><br></div>'
            '<div style="line-height:1.5"><span style="color:rgb(68,68,68);font-family:sans-serif;font-size:12px">'
            'Cell: +1 650 495-6150</span></div><div style="color:rgb(68,68,68);font-family:sans-serif;line-height:1.5;font-size:12px">'
            '<a href="https://www.plugandplaytechcenter.com/" rel="noopener" style="color:rgb(17,85,204)" target="_blank">'
            'plugandplaytechcenter.com</a></div></div></div></div></div>'
        )
        signature_plain = "Hendrik Cornelissen\nInvestment Team\n\nCell: +1 650 495-6150\nplugandplaytechcenter.com"

        emails_with_gmail_sig = [
            {
                'text': f"Hello team,\n\nHere is the report.\n\n{signature_plain}",
                'html': f'<html><body><p>Hello team,</p><p>Here is the report.</p>{signature_html}</body></html>'
            },
            {
                'text': f"Hi,\n\nPlease review this document.\n\n{signature_plain}",
                'html': f'<html><body><p>Hi,</p><p>Please review this document.</p>{signature_html}</body></html>'
            },
            {
                'text': f"Team,\n\nFYI.\n\n{signature_plain}",
                'html': f'<html><body><p>Team,</p><p>FYI.</p>{signature_html}</body></html>'
            }
        ]

        # Act
        plain_signature, html_signature = IMAPService._find_best_signature(emails_with_gmail_sig)

        # Assert
        soup_expected = BeautifulSoup(signature_html, 'lxml')
        soup_actual = BeautifulSoup(html_signature, 'lxml')

        self.assertEqual(signature_plain.strip(), plain_signature.strip())
        self.assertEqual(str(soup_expected), str(soup_actual))

if __name__ == '__main__':
    unittest.main() 
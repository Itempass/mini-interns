import unittest
from mcp_servers.imap_mcpserver.src.imap_client.models import EmailMessage, EmailThread

class TestEmailThreadSorting(unittest.TestCase):

    def test_from_messages_sorts_by_date_with_timezones(self):
        """
        Tests that EmailThread.from_messages correctly sorts emails by date,
        especially when different timezones are involved.
        """
        # These messages are intentionally out of order based on naive string sorting of dates
        messages = [
            EmailMessage(
                uid="1",
                message_id="<message_hendrik_reply@mail.gmail.com>",
                from_="Hendrik Cornelissen <h.cornelissen@pnptc.com>",
                to="xiao@altohealth.io",
                subject="Re: Follow Up from Alto Health",
                date="Thu, 26 Jun 2025 07:51:32 -0700", # 2025-06-26 14:51:32 UTC
                body_raw="", body_markdown="", body_cleaned=""
            ),
            EmailMessage(
                uid="2",
                message_id="<message_xiao_initial@mail.gmail.com>",
                from_="Xiao Zhang <xiao@altohealth.io>",
                to="h.cornelissen@pnptc.com",
                subject="Follow Up from Alto Health",
                date="Thu, 26 Jun 2025 12:41:52 +0100", # 2025-06-26 11:41:52 UTC
                body_raw="", body_markdown="", body_cleaned=""
            ),
            EmailMessage(
                uid="3",
                message_id="<message_xiao_reply@mail.gmail.com>",
                from_="Xiao Zhang <xiao@altohealth.io>",
                to="Hendrik Cornelissen <h.cornelissen@pnptc.com>",
                subject="Re: Follow Up from Alto Health",
                date="Thu, 26 Jun 2025 16:47:34 +0100", # 2025-06-26 15:47:34 UTC
                body_raw="", body_markdown="", body_cleaned=""
            ),
        ]

        thread = EmailThread.from_messages(messages, "thread-id-123")

        self.assertEqual(len(thread.messages), 3)

        sorted_message_ids = [msg.message_id for msg in thread.messages]
        expected_order = [
            "<message_xiao_initial@mail.gmail.com>",
            "<message_hendrik_reply@mail.gmail.com>",
            "<message_xiao_reply@mail.gmail.com>"
        ]
        self.assertEqual(sorted_message_ids, expected_order)

if __name__ == '__main__':
    unittest.main() 
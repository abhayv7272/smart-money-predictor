import os
import sys
import unittest
from email import message_from_string
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from email_sender import EmailSender


class EmailDeliveryTests(unittest.TestCase):
    def test_missing_smtp_credentials_are_explicit_and_can_be_required(self):
        with patch.dict(os.environ, {"MAIL_USERNAME": "", "MAIL_PASSWORD": "", "REQUIRE_EMAIL": ""}, clear=False):
            sent = EmailSender("reader@example.com").send_report("subject", "<html></html>")
            self.assertFalse(sent)
        with patch.dict(os.environ, {"MAIL_USERNAME": "", "MAIL_PASSWORD": "", "REQUIRE_EMAIL": "true"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "SMTP credentials"):
                EmailSender("reader@example.com").send_report("subject", "<html></html>")

    def test_smtp_dispatch_is_bounded_and_embeds_chart_data_as_cid(self):
        smtp = Mock()
        smtp.__enter__ = Mock(return_value=smtp)
        smtp.__exit__ = Mock(return_value=False)
        payload = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jX7sAAAAASUVORK5CYII="
        html = f'<html><img src="data:image/png;base64,{payload}"></html>'
        env = {
            "MAIL_SERVER": "smtp.example.com",
            "MAIL_PORT": "587",
            "MAIL_USERNAME": "bot@example.com",
            "MAIL_PASSWORD": "password",
            "MAIL_FROM": "bot@example.com",
            "REQUIRE_EMAIL": "true",
        }
        with patch.dict(os.environ, env, clear=False), patch("email_sender.smtplib.SMTP", return_value=smtp) as smtp_factory:
            sent = EmailSender("reader@example.com").send_report("subject", html)
        self.assertTrue(sent)
        smtp_factory.assert_called_once_with("smtp.example.com", 587, timeout=20)
        smtp.starttls.assert_called_once()
        message = message_from_string(smtp.sendmail.call_args.args[2])
        html_part = next(part for part in message.walk() if part.get_content_type() == "text/html")
        html_body = html_part.get_payload(decode=True).decode("utf-8")
        self.assertIn("cid:signal_chart_0", html_body)
        self.assertTrue(any(part.get("Content-ID") == "<signal_chart_0>" for part in message.walk()))
        self.assertIn("signal_chart_0.png", smtp.sendmail.call_args.args[2])


if __name__ == "__main__":
    unittest.main()

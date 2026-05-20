import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import email_delivery as module


class EmailDeliveryTests(unittest.TestCase):
    def test_resolve_email_recipient_prefers_email_recipient(self) -> None:
        with patch.dict(module.os.environ, {"EMAIL_RECIPIENT": "to@example.com"}, clear=True):
            recipient, source = module.resolve_email_recipient()
        self.assertEqual(recipient, "to@example.com")
        self.assertEqual(source, "EMAIL_RECIPIENT")

    def test_resolve_email_recipient_raises_without_config(self) -> None:
        with patch.dict(module.os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                module.resolve_email_recipient()

    def test_get_email_client_prefers_endpoint(self) -> None:
        env = {"ACS_ENDPOINT": "https://example.communication.azure.com"}
        with patch.dict(module.os.environ, env, clear=True):
            with patch("email_delivery.EmailClient") as client_cls:
                with patch("email_delivery.DefaultAzureCredential", return_value=object()):
                    module.get_email_client()
        client_cls.assert_called_once()

    def test_send_email_via_acs(self) -> None:
        env = {"ACS_EMAIL_SENDER_ADDRESS": "DoNotReply@example.azurecomm.net"}
        fake_result = SimpleNamespace(status="Queued")
        fake_poller = SimpleNamespace(result=MagicMock(return_value=fake_result))
        fake_client = SimpleNamespace(begin_send=MagicMock(return_value=fake_poller))

        with patch.dict(module.os.environ, env, clear=True):
            with patch("email_delivery.get_email_client", return_value=fake_client):
                recipient = module.send_email_via_acs(
                    subject="Subject",
                    body="Body",
                    recipient="to@example.com",
                )

        self.assertEqual(recipient, "to@example.com")
        fake_client.begin_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()

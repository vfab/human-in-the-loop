import unittest
from types import SimpleNamespace
from unittest.mock import patch

import group_chat_request_info as module


class GroupChatHelpersTests(unittest.TestCase):
    def test_safe_attr(self) -> None:
        obj = SimpleNamespace(value=10)
        self.assertEqual(module._safe_attr(obj, "value"), 10)
        self.assertEqual(module._safe_attr(obj, "missing", "fallback"), "fallback")

    def test_normalize_summary_lines_prefers_conversation(self) -> None:
        role = SimpleNamespace(value="assistant")
        messages = [SimpleNamespace(text="Hi", role=role, author_name="optimist")]

        lines = module._normalize_summary_lines(messages, ["[assistant]: streamed"])

        self.assertEqual(lines, ["[optimist]: Hi"])

    def test_normalize_summary_lines_falls_back_to_stream(self) -> None:
        lines = module._normalize_summary_lines([], ["", "[assistant]: streamed"])
        self.assertEqual(lines, ["[assistant]: streamed"])

    def test_resolve_email_recipient(self) -> None:
        with patch.dict(module.os.environ, {"SMTP_USER": "smtp@example.com"}, clear=True):
            recipient, source = module._resolve_email_recipient()
        self.assertEqual(recipient, "smtp@example.com")
        self.assertEqual(source, "SMTP_USER fallback")

    def test_request_email_send_approval(self) -> None:
        with patch("builtins.input", side_effect=["y"]):
            self.assertTrue(module.request_email_send_approval("summary", "to@example.com"))
        with patch("builtins.input", side_effect=["N"]):
            self.assertFalse(module.request_email_send_approval("summary", "to@example.com"))


if __name__ == "__main__":
    unittest.main()

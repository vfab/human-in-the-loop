import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import concurrent_request_info as module


class ConcurrentHelpersTests(unittest.TestCase):
    def test_role_to_text_handles_enum_like_role(self) -> None:
        role = SimpleNamespace(value="USER")
        self.assertEqual(module._role_to_text(role), "user")

    def test_resolve_email_recipient_precedence(self) -> None:
        with patch.dict(module.os.environ, {"EMAIL_RECIPIENT": "primary@example.com"}, clear=True):
            recipient, source = module._resolve_email_recipient()
        self.assertEqual(recipient, "primary@example.com")
        self.assertEqual(source, "EMAIL_RECIPIENT")

    def test_resolve_email_recipient_raises_without_values(self) -> None:
        with patch.dict(module.os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                module._resolve_email_recipient()

    def test_request_email_send_approval(self) -> None:
        with patch("builtins.input", side_effect=["yes"]):
            self.assertTrue(module.request_email_send_approval("summary", "to@example.com"))
        with patch("builtins.input", side_effect=["n"]):
            self.assertFalse(module.request_email_send_approval("summary", "to@example.com"))

    def test_send_summary_email_via_smtp(self) -> None:
        with patch("concurrent_request_info._resolve_email_recipient", return_value=("recipient@example.com", "EMAIL_RECIPIENT")):
            with patch("concurrent_request_info.send_email_via_acs") as mock_send:
                recipient = module.send_summary_email_via_smtp("hello")

        self.assertEqual(recipient, "recipient@example.com")
        mock_send.assert_called_once_with(
            subject="LLM Impact Analysis - Concurrent HITL Summary",
            body="hello",
            recipient="recipient@example.com",
        )


class ConcurrentAggregationTests(unittest.IsolatedAsyncioTestCase):
    async def test_aggregate_with_synthesis_uses_chat_client(self) -> None:
        fake_chat_client = SimpleNamespace(
            get_response=AsyncMock(
                return_value=SimpleNamespace(messages=[SimpleNamespace(text="Synthesized")])
            )
        )

        module._chat_client = fake_chat_client

        result_item = SimpleNamespace(
            executor_id="technical_analyst",
            agent_response=SimpleNamespace(messages=[SimpleNamespace(text="Technical output")]),
            full_conversation=[SimpleNamespace(role="user", text="Prioritize reliability")],
        )

        result = await module.aggregate_with_synthesis([result_item])

        self.assertEqual(result, "Synthesized")
        fake_chat_client.get_response.assert_awaited_once()

    async def test_aggregate_with_synthesis_without_client(self) -> None:
        module._chat_client = None
        result = await module.aggregate_with_synthesis([])
        self.assertIn("not initialized", result)


if __name__ == "__main__":
    unittest.main()

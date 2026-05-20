import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import agents_with_approval_requests as module


class EmailAssistantTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_email_marks_important_sender(self) -> None:
        fake_agent = SimpleNamespace(run=AsyncMock(return_value=SimpleNamespace(text="Draft")))
        fake_client = SimpleNamespace(as_agent=MagicMock(return_value=fake_agent))

        assistant = module.EmailAssistant(fake_client)
        email = module.Email(
            recipient="team@example.com",
            sender="sam@example.com",
            subject="Status",
            body="Any updates?",
        )

        response = await assistant.process_email(email)

        self.assertEqual(response, "Draft")
        called_message = fake_agent.run.await_args.args[0]
        self.assertIn("IMPORTANT EMAIL FROM KEY TEAM MEMBER", called_message)
        self.assertIn("Subject: Status", called_message)


class EmailWorkflowHelpersTests(unittest.TestCase):
    def test_email_str_representation(self) -> None:
        email = module.Email(
            recipient="team@example.com",
            sender="sam@example.com",
            subject="Hello",
            body="Body",
        )

        rendered = str(email)
        self.assertIn("To: team@example.com", rendered)
        self.assertIn("From: sam@example.com", rendered)
        self.assertIn("Subject: Hello", rendered)

    def test_request_human_approval_approve(self) -> None:
        email = module.Email("a@example.com", "b@example.com", "Subject", "Body")
        with patch("builtins.input", side_effect=["a"]):
            approved = module.request_human_approval(email, "Draft")
        self.assertEqual(approved, "Draft")

    def test_request_human_approval_edit(self) -> None:
        email = module.Email("a@example.com", "b@example.com", "Subject", "Body")
        with patch("builtins.input", side_effect=["e", "Line 1", "Line 2", "."]):
            approved = module.request_human_approval(email, "Draft")
        self.assertEqual(approved, "Line 1\nLine 2")

    def test_request_human_approval_reject(self) -> None:
        email = module.Email("a@example.com", "b@example.com", "Subject", "Body")
        with patch("builtins.input", side_effect=["r"]):
            approved = module.request_human_approval(email, "Draft")
        self.assertIsNone(approved)

    def test_send_email_via_smtp_uses_acs_helper(self) -> None:
        email = module.Email("ignored@example.com", "sender@example.com", "Subject", "Body")
        with patch("agents_with_approval_requests.send_email_via_acs") as mock_send:
            module.send_email_via_smtp(email, "Generated body")

        mock_send.assert_called_once_with(
            subject="Re: Subject",
            body="Generated body",
            recipient="ignored@example.com",
        )


if __name__ == "__main__":
    unittest.main()

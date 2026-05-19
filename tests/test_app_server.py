import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import app_server


class AppServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app_server.app)

    def test_run_endpoint_returns_agent_response(self) -> None:
        payload = {
            "sender": "sam@example.com",
            "subject": "Status update",
            "body": "Please share the latest status.",
        }

        with patch.object(
            app_server.assistant,
            "process_email",
            AsyncMock(return_value="Thanks for the update."),
        ):
            response = self.client.post("/run", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "Thanks for the update."})

    def test_run_endpoint_returns_http_500_on_agent_error(self) -> None:
        payload = {
            "sender": "sam@example.com",
            "subject": "Status update",
            "body": "Please share the latest status.",
        }

        with patch.object(
            app_server.assistant,
            "process_email",
            AsyncMock(side_effect=RuntimeError("service unavailable")),
        ):
            response = self.client.post("/run", json=payload)

        self.assertEqual(response.status_code, 500)
        self.assertIn("Error processing email", response.json()["detail"])

    def test_run_endpoint_integration_uses_process_email_preprocessing(self) -> None:
        payload = {
            "sender": "sam@example.com",
            "subject": "Status update",
            "body": "Please share the latest status.",
        }

        fake_run = AsyncMock(return_value=SimpleNamespace(text="Draft response"))
        with patch.object(app_server.assistant.agent, "run", fake_run):
            response = self.client.post("/run", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "Draft response"})
        called_message = fake_run.await_args.args[0]
        self.assertIn("IMPORTANT EMAIL FROM KEY TEAM MEMBER", called_message)
        self.assertIn("Subject: Status update", called_message)

    def test_run_endpoint_validates_required_fields(self) -> None:
        response = self.client.post("/run", json={"sender": "sam@example.com"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()

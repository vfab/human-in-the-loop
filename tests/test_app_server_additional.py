import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import app_server


class AppServerAdditionalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app_server.app)

    def test_root_endpoint_serves_frontend(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("HITL Workflow Dashboard", response.text)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_run_endpoint_full_flow_for_non_priority_sender(self) -> None:
        payload = {
            "sender": "alex@example.com",
            "subject": "Weekly update",
            "body": "Please send a summary.",
        }

        fake_run = AsyncMock(return_value=SimpleNamespace(text="Summary sent"))
        with patch.object(app_server.assistant.agent, "run", fake_run):
            response = self.client.post("/run", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "Summary sent"})

        called_message = fake_run.await_args.args[0]
        self.assertIn("From: alex@example.com", called_message)
        self.assertNotIn("IMPORTANT EMAIL FROM KEY TEAM MEMBER", called_message)


if __name__ == "__main__":
    unittest.main()

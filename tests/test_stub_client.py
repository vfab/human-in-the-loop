import json
import unittest

import stub_client as module


class StubClientTests(unittest.IsolatedAsyncioTestCase):
    def test_extract_text_supports_str_and_list(self) -> None:
        self.assertEqual(module._extract_text("hello"), "hello")
        self.assertEqual(
            module._extract_text([{"text": "hello"}, {"content": "world"}]),
            "hello world",
        )

    def test_pick_response_routes_guessing_prompt(self) -> None:
        payload = {
            "messages": [
                {"role": "system", "content": "You are playing a guessing game"},
                {"role": "user", "content": "Please guess 42"},
            ]
        }
        result = module._pick_response(json.dumps(payload).encode())
        self.assertEqual(result, "42")

    async def test_stub_transport_returns_json_completion(self) -> None:
        transport = module._StubTransport()
        payload = {
            "model": "stub",
            "messages": [
                {"role": "system", "content": "You are a technical analyst"},
                {"role": "user", "content": "Analyze"},
            ],
            "stream": False,
        }

        request = module.httpx.Request(
            "POST",
            "https://example.invalid/v1/chat/completions",
            content=json.dumps(payload).encode(),
        )
        response = await transport.handle_async_request(request)

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode())
        self.assertEqual(body["object"], "chat.completion")
        self.assertEqual(body["choices"][0]["message"]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()

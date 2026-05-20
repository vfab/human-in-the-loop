import unittest
from types import SimpleNamespace

import guessing_game_with_human_input as module


class FakeCtx:
    def __init__(self) -> None:
        self.sent_messages = []
        self.request_infos = []
        self.outputs = []

    async def send_message(self, message) -> None:
        self.sent_messages.append(message)

    async def request_info(self, request_data, response_type) -> None:
        self.request_infos.append((request_data, response_type))

    async def yield_output(self, output) -> None:
        self.outputs.append(output)


class TurnManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_sends_initial_message(self) -> None:
        manager = module.TurnManager()
        ctx = FakeCtx()

        await manager.start("start", ctx)

        self.assertEqual(len(ctx.sent_messages), 1)
        self.assertEqual(len(ctx.sent_messages[0].messages), 1)
        self.assertIn("first guess", ctx.sent_messages[0].messages[0].text.lower())

    async def test_on_agent_response_requests_feedback_when_guess_found(self) -> None:
        manager = module.TurnManager()
        ctx = FakeCtx()
        result = SimpleNamespace(agent_response=SimpleNamespace(text="My guess is 42"))

        await manager.on_agent_response(result, ctx)

        self.assertEqual(manager.game_state.last_guess, 42)
        self.assertEqual(len(ctx.request_infos), 1)
        prompt = ctx.request_infos[0][0].prompt
        self.assertIn("The agent guessed: 42", prompt)

    async def test_on_agent_response_requests_feedback_when_guess_missing(self) -> None:
        manager = module.TurnManager()
        ctx = FakeCtx()
        result = SimpleNamespace(agent_response=SimpleNamespace(text="I cannot decide"))

        await manager.on_agent_response(result, ctx)

        self.assertEqual(len(ctx.request_infos), 1)
        prompt = ctx.request_infos[0][0].prompt
        self.assertIn("could not parse", prompt)

    async def test_on_human_feedback_correct_yields_output(self) -> None:
        manager = module.TurnManager()
        manager.game_state.last_guess = 69
        ctx = FakeCtx()

        await manager.on_human_feedback(module.HumanFeedbackRequest("prompt"), "correct", ctx)

        self.assertEqual(ctx.outputs, ["Guessed correctly: 69"])

    async def test_on_human_feedback_updates_bounds_and_sends_next_guess(self) -> None:
        manager = module.TurnManager()
        manager.game_state.last_guess = 50
        ctx = FakeCtx()

        await manager.on_human_feedback(module.HumanFeedbackRequest("prompt"), "higher", ctx)

        self.assertEqual(manager.game_state.lower_bound, 51)
        self.assertEqual(len(ctx.sent_messages), 1)
        self.assertEqual(len(ctx.sent_messages[0].messages), 1)
        self.assertIn("number is between", ctx.sent_messages[0].messages[0].text.lower())


if __name__ == "__main__":
    unittest.main()

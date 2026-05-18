# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import os
import re
from dataclasses import dataclass

from agent_framework import (
    AgentExecutorRequest,  # Message bundle sent to an AgentExecutor
    AgentExecutorResponse,
    Executor,  # Base class for workflow executors
    Message,  # Chat message structure
    WorkflowEvent,
    WorkflowBuilder,  # Fluent builder for assembling the graph
    WorkflowContext,  # Per run context and event bus
    WorkflowRunState,  # Enum of workflow run states
    handler,
    response_handler,  # Decorator to expose an Executor method as a step
)
from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
Sample: Human in the loop guessing game

An agent guesses a number, then a human guides it with higher, lower, or
correct. The loop continues until the human confirms correct, at which point
the workflow completes when idle with no pending work.

Purpose:
Show how to integrate a human step in the middle of an LLM workflow by using
`request_info` and `send_responses_streaming`.

Demonstrate:
- Alternating turns between an AgentExecutor and a human, driven by events.
- Using Pydantic response_format to enforce structured JSON output from the agent instead of regex parsing.
- Driving the loop in application code with run_stream and responses parameter.

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, executors, edges, events, and streaming runs.
"""

# How human-in-the-loop is achieved via `request_info` and `send_responses_streaming`:
# - An executor (TurnManager) calls `ctx.request_info` with a payload (HumanFeedbackRequest).
# - The workflow run pauses and emits a RequestInfoEvent with the payload and the request_id.
# - The application captures the event, prompts the user, and collects replies.
# - The application calls `send_responses_streaming` with a map of request_ids to replies.
# - The workflow resumes, and the response is delivered to the executor method decorated with @response_handler.
# - The executor can then continue the workflow, e.g., by sending a new message to the agent.

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class HumanFeedbackRequest:
    """Request sent to the human for feedback on the agent's guess."""

    prompt: str


@dataclass
class GuessingGameState:
    """Tracks the state of the guessing game for smarter guessing."""

    lower_bound: int = 1
    upper_bound: int = 100
    last_guess: int | None = None
class TurnManager(Executor):
    """Coordinates turns between the agent and the human.

    Responsibilities:
    - Kick off the first agent turn.
    - After each agent reply, request human feedback with a HumanFeedbackRequest.
    - After each human reply, either finish the game or prompt the agent again with feedback.
    """

    def __init__(self, id: str | None = None):
        super().__init__(id=id or "turn_manager")
        self.game_state = GuessingGameState()

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """Start the game by asking the agent for an initial guess.

        Contract:
        - Input is a simple starter token (ignored here).
        - Output is an AgentExecutorRequest that triggers the agent to produce a guess.
        """
        user = Message("user", ["Start by making your first guess of a number between 1 and 100."])
        await ctx.send_message(AgentExecutorRequest(messages=[user], should_respond=True))

    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext,
    ) -> None:
        """Handle the agent's guess and request human guidance.

        Steps:
        1) Parse the agent's output to extract the guess.
        2) Update game state bounds based on feedback.
        3) Request info with a HumanFeedbackRequest as the payload.
        """
        # Parse model output and extract first integer guess (1-100).
        text = result.agent_response.text or ""
        match = re.search(r"\b([1-9][0-9]?|100)\b", text)
        if not match:
            await ctx.request_info(
                request_data=HumanFeedbackRequest(
                    prompt=(
                        "I could not parse the agent guess. Type one of: higher, much higher, lower, much lower, correct, or exit. "
                        f"Raw agent output: {text}"
                    )
                ),
                response_type=str,
            )
            return

        last_guess = int(match.group(1))
        self.game_state.last_guess = last_guess

        # Craft a precise human prompt that defines the feedback options.
        prompt = (
            f"The agent guessed: {last_guess}. "
            "Type one of: higher (closer but still higher), much higher (significantly higher), "
            "lower (closer but still lower), much lower (significantly lower), correct, or exit."
        )
        # Send a request with a prompt as the payload and expect a string reply.
        await ctx.request_info(
            request_data=HumanFeedbackRequest(prompt=prompt),
            response_type=str,
        )

    @response_handler
    async def on_human_feedback(
        self,
        original_request: HumanFeedbackRequest,
        feedback: str,
        ctx: WorkflowContext[AgentExecutorRequest, str],
    ) -> None:
        """Continue the game or finish based on human feedback."""
        logger.debug("Feedback for prompt %r received: %s", original_request.prompt, feedback)

        reply = feedback.strip().lower()

        if reply == "correct":
            if self.game_state.last_guess:
                await ctx.yield_output(f"Guessed correctly: {self.game_state.last_guess}")
            else:
                await ctx.yield_output("Guessed correctly!")
            return

        # Update bounds based on feedback for smarter guessing.
        if reply in ["higher", "much higher"]:
            self.game_state.lower_bound = (self.game_state.last_guess or self.game_state.lower_bound) + 1
        elif reply in ["lower", "much lower"]:
            self.game_state.upper_bound = (self.game_state.last_guess or self.game_state.upper_bound) - 1

        # Calculate next guess using binary search strategy.
        next_guess = (self.game_state.lower_bound + self.game_state.upper_bound) // 2
        
        # Provide feedback to the agent to try again with smart guidance.
        feedback_description = {
            "higher": "a bit higher",
            "much higher": "much higher",
            "lower": "a bit lower",
            "much lower": "much lower",
        }.get(reply, reply)
        
        user_msg = Message(
            "user",
            [
                (
                    f"Feedback: your guess should be {feedback_description}. "
                    f"The number is between {self.game_state.lower_bound} and {self.game_state.upper_bound}. "
                    f"Please guess {next_guess}."
                )
            ],
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))


def create_guessing_agent():
    """Create the guessing agent with instructions to guess a number between 1 and 100."""
    api_version = "2024-12-01-preview"
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    model = os.getenv("AZURE_OPENAI_CHAT_MODEL") or os.getenv("AZURE_OPENAI_MODEL")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if not endpoint or not model:
        raise ValueError(
            "Missing Azure OpenAI config. Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_MODEL (or AZURE_OPENAI_MODEL)."
        )

    if api_key:
        chat_client = OpenAIChatCompletionClient(
            model=model,
            azure_endpoint=endpoint,
            api_version=api_version,
            api_key=api_key,
        )
    else:
        chat_client = OpenAIChatCompletionClient(
            model=model,
            azure_endpoint=endpoint,
            api_version=api_version,
            credential=AzureCliCredential(),
        )

    return chat_client.as_agent(
        name="GuessingAgent",
        instructions=(
            "You are playing a guessing game to find a number between 1 and 100. "
            "The human will give you feedback: 'higher' (your guess is too low, but close), "
            "'much higher' (your guess is too low by a lot), 'lower' (your guess is too high, but close), "
            "'much lower' (your guess is too high by a lot). "
            "Use binary search strategy: narrow down the range quickly. "
            "When you receive feedback with specific bounds, use them to calculate the midpoint. "
            "You MUST return only the guessed integer (for example: 50). "
            "No explanations or additional text."
        ),
    )


async def main() -> None:
    """Run the human-in-the-loop guessing game workflow."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s  %(message)s")

    # Build a simple loop: TurnManager <-> AgentExecutor.
    turn_manager = TurnManager(id="turn_manager")
    guessing_agent = create_guessing_agent()
    workflow = (
        WorkflowBuilder(start_executor=turn_manager)
        .add_edge(turn_manager, guessing_agent)  # Ask agent to make/adjust a guess
        .add_edge(guessing_agent, turn_manager)  # Agent's response comes back to coordinator
    ).build()

    # Human in the loop run: alternate between invoking the workflow and supplying collected responses.
    pending_responses: dict[str, str] | None = None
    workflow_output: str | None = None
    output_chunks: list[str] = []

    # User guidance printing:
    # If you want to instruct users up front, print a short banner before the loop.
    # Example:
    # print(
    #     "Interactive mode. When prompted, type one of: higher, lower, correct, or exit. "
    #     "The agent will keep guessing until you reply correct.",
    #     flush=True,
    # )

    while workflow_output is None:
        # First iteration starts the workflow. Subsequent iterations resume with pending responses.
        stream = (
            workflow.run(responses=pending_responses, stream=True)
            if pending_responses
            else workflow.run("start", stream=True)
        )

        events = [event async for event in stream]
        pending_responses = None

        # Collect human requests, workflow outputs, and check for completion.
        requests: list[tuple[str, str]] = []  # (request_id, prompt)
        for event in events:
            if isinstance(event, WorkflowEvent) and event.type == "request_info" and isinstance(event.data, HumanFeedbackRequest):
                # RequestInfoEvent for our HumanFeedbackRequest.
                requests.append((event.request_id, event.data.prompt))
            elif isinstance(event, WorkflowEvent) and event.type == "output":
                # Capture streamed output chunks, but ignore empty updates.
                chunk = str(event.data or "")
                if chunk.strip() and "Guessed correctly" in chunk:
                    output_chunks.append(chunk)

        reached_idle = any(
            isinstance(e, WorkflowEvent) and e.type == "status" and e.state == WorkflowRunState.IDLE for e in events
        )

        if reached_idle and not requests:
            consolidated = "".join(output_chunks).strip()
            workflow_output = consolidated if consolidated else "Workflow ended without final output."

        # Optional state print for developer visibility.
        idle_with_requests = any(
            isinstance(e, WorkflowEvent) and e.type == "status" and e.state != WorkflowRunState.IDLE
            for e in events
        )
        if idle_with_requests and requests:
            logger.debug("State: awaiting human input")

        # If we have any human requests, prompt the user and prepare responses.
        if requests:
            responses: dict[str, str] = {}
            for req_id, prompt in requests:
                # Simple console prompt for the sample.
                print(f"HITL> {prompt}")
                # Instructional print already appears above. The input line below is the user entry point.
                # If desired, you can add more guidance here, but keep it concise.
                answer = input("Enter higher/much higher/lower/much lower/correct/exit: ").lower()  # noqa: ASYNC250
                if answer == "exit":
                    logger.info("Exiting")
                    return
                responses[req_id] = answer
            pending_responses = responses

    # Show final result from workflow output captured during streaming.
    logger.info("Workflow output: %s", workflow_output)
    """
    Sample Output:

    HITL> The agent guessed: 50. Type one of: higher (closer but still higher), much higher (significantly higher), lower (closer but still lower), much lower (significantly lower), correct, or exit.
    Enter higher/much higher/lower/much lower/correct/exit: much higher
    HITL> The agent guessed: 75. Type one of: higher (closer but still higher), much higher (significantly higher), lower (closer but still lower), much lower (significantly lower), correct, or exit.
    Enter higher/much higher/lower/much lower/correct/exit: lower
    HITL> The agent guessed: 62. Type one of: higher (closer but still higher), much higher (significantly higher), lower (closer but still lower), much lower (significantly lower), correct, or exit.
    Enter higher/much higher/lower/much lower/correct/exit: higher
    HITL> The agent guessed: 69. Type one of: higher (closer but still higher), much higher (significantly higher), lower (closer but still lower), much lower (significantly lower), correct, or exit.
    Enter higher/much higher/lower/much lower/correct/exit: correct
    Workflow output: Guessed correctly: 69
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())

# Copyright (c) Microsoft. All rights reserved.

"""
Game Workflow - Interactive number guessing game.

Extracted from: guessing_game_with_human_input.py

This workflow demonstrates an interactive game where an agent guesses
a number and a human provides feedback (higher/lower/correct) until
the agent guesses correctly.

Flow:
1. Agent makes initial guess
2. Human provides feedback (higher/lower/correct)
3. Loop until agent guesses correctly
4. Workflow completes on successful guess
"""

import logging
import re
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    Message,
    WorkflowEvent,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowRunState,
    handler,
    response_handler,
)
from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential

from . import WorkflowConfig, reply_text

logger = logging.getLogger(__name__)

DEFAULT_MAX_NUMBER = 10


def _parse_max_number(value: str | int) -> int:
    """Parse the selected range, falling back to the default for blank/invalid input."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_NUMBER
    return number if 2 <= number <= 1000 else DEFAULT_MAX_NUMBER


@dataclass
class HumanFeedbackRequest:
    """Request sent to human for feedback on agent's guess."""
    prompt: str


class TurnManager(Executor):
    """Coordinates turns between agent and human in the guessing game."""
    
    def __init__(self, id: str = "turn_manager", max_number: int = 10):
        super().__init__(id=id)
        self.max_number = max_number
    
    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """Start the game by asking agent for initial guess."""
        user = Message(
            "user",
            [f"Start by making your first guess. Guess a number between 1 and {self.max_number}."],
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user], should_respond=True))
    
    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext,
    ) -> None:
        """Handle agent's guess and request human feedback."""
        # Parse agent output to extract guess
        text = result.agent_response.text or ""
        match = next(
            (m for m in re.finditer(r"\b\d+\b", text) if 1 <= int(m.group()) <= self.max_number),
            None,
        )
        
        if not match:
            await ctx.request_info(
                request_data=HumanFeedbackRequest(
                    prompt=(
                        "I could not parse the agent's guess. "
                        "Type one of: higher, lower, correct, or exit. "
                        f"Raw agent output: {text}"
                    )
                ),
                response_type=str,
            )
            return
        
        last_guess = int(match.group())
        
        # Request human feedback
        prompt = (
            f"The agent guessed: {last_guess}. "
            "Type: higher (number is higher), lower (number is lower), correct, or exit."
        )
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
        """Continue game or finish based on human feedback."""
        logger.debug("Feedback received for prompt: %s -> %s", original_request.prompt, feedback)
        
        reply = feedback.strip().lower()
        
        if reply == "correct":
            await ctx.yield_output("Guessed correctly!")
            return
        
        if reply == "exit":
            await ctx.yield_output("Game exited by user.")
            return
        
        # Provide feedback to agent for next guess
        if reply == "higher":
            feedback_msg = "higher"
        elif reply == "lower":
            feedback_msg = "lower"
        else:
            feedback_msg = reply
        
        user_msg = Message(
            "user",
            [
                f"Feedback: {feedback_msg}. "
                f"Return only your next guess as a single integer between 1 and {self.max_number}."
            ],
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))


async def run_game_workflow(
    config: WorkflowConfig,
    max_number: str | int = DEFAULT_MAX_NUMBER,
) -> AsyncIterator[WorkflowEvent]:
    """Run the guessing game workflow.
    
    Demonstrates interactive human-in-the-loop game where agent
    guesses a number and human provides feedback.
    
    Args:
        config: WorkflowConfig with Azure OpenAI settings
        max_number: Upper bound of the range the human thinks of (default 10)
        
    Yields:
        WorkflowEvent objects for dashboard consumption
    """
    upper = _parse_max_number(max_number)
    
    # Validate configuration
    config_error = config.validate()
    if config_error:
        yield WorkflowEvent(
            type="error",
            data={"message": config_error},
            source_executor_id="system"
        )
        return
    
    try:
        # Initialize chat client
        api_version = config.azure_openai_api_version
        
        if config.azure_openai_api_key:
            chat_client = OpenAIChatCompletionClient(
                model=config.azure_openai_chat_deployment,
                azure_endpoint=config.azure_openai_endpoint,
                api_version=api_version,
                api_key=config.azure_openai_api_key,
            )
        else:
            chat_client = OpenAIChatCompletionClient(
                model=config.azure_openai_chat_deployment,
                azure_endpoint=config.azure_openai_endpoint,
                api_version=api_version,
                credential=AzureCliCredential(),
            )
        
        logger.info("Starting guessing game workflow")
        
        # Create guessing agent
        guesser_agent = chat_client.as_agent(
            name="guesser",
            instructions=(
                "You are playing a number guessing game. The human will tell you "
                "if your guess is too high or too low. Use this feedback to narrow "
                "down to the correct number. Always respond with just a number."
            ),
        )
        
        # Build workflow
        turn_manager = TurnManager(id="turn_manager", max_number=upper)
        
        workflow = (
            WorkflowBuilder(
                name="Number Guessing Game",
                description="Interactive game where agent guesses a number",
                start_executor=turn_manager,
            )
            .add_edge(turn_manager, guesser_agent)
            .add_edge(guesser_agent, turn_manager)
            .build()
        )
        
        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"Starting guessing game. Think of a number between 1 and {upper}..."},
            source_executor_id="system"
        )
        
        # Run workflow with human-in-the-loop
        pending_responses: Optional[dict[str, str]] = None
        workflow_complete = False
        guess_count = 0
        
        while not workflow_complete:
            # Run or continue workflow
            stream = (
                workflow.run(responses=pending_responses, stream=True)
                if pending_responses
                else workflow.run("", stream=True)
            )
            
            pending_responses = None
            
            # Process events
            async for event in stream:
                if isinstance(event, WorkflowEvent) and event.type == "request_info":
                    # Human feedback requested
                    request_data = event.data
                    if isinstance(request_data, HumanFeedbackRequest):
                        reply = yield WorkflowEvent(
                            type="input_required",
                            data={
                                "request_id": event.request_id,
                                "prompt": request_data.prompt,
                                "options": ["higher", "lower", "correct", "exit"]
                            },
                            source_executor_id="system"
                        )
                        
                        guess_count += 1
                        # Blank or timed-out replies end the game rather than loop forever
                        answer = reply_text(reply).lower() or "exit"
                        yield WorkflowEvent(
                            type="agent_message",
                            data={"agent": "you", "content": answer},
                            source_executor_id="you"
                        )
                        pending_responses = {event.request_id: answer}
                
                elif isinstance(event, WorkflowEvent) and event.type == "agent_output":
                    # Agent made a guess
                    yield WorkflowEvent(
                        type="agent_message",
                        data={
                            "agent": "guesser",
                            "content": f"Guess #{guess_count}: {event.data}"
                        },
                        source_executor_id="guesser"
                    )
                
                elif isinstance(event, WorkflowEvent) and event.type == "output":
                    # The guesser agent also streams its text as output events;
                    # only the turn manager's output means the game is over.
                    if event.executor_id == "turn_manager":
                        logger.info("Guessing game complete")
                        if event.data:
                            yield WorkflowEvent(
                                type="agent_message",
                                data={"content": str(event.data)},
                                source_executor_id="system"
                            )
                        workflow_complete = True
                
                elif isinstance(event, WorkflowEvent) and event.type == "status":
                    if event.state == WorkflowRunState.IDLE:
                        workflow_complete = True
        
        yield WorkflowEvent(
            type="workflow_complete",
            data={"status": "completed", "guesses": guess_count},
            source_executor_id="system"
        )
    
    except Exception as e:
        logger.exception("Error in game workflow: %s", e)
        yield WorkflowEvent(
            type="error",
            data={"message": str(e)},
            source_executor_id="system"
        )

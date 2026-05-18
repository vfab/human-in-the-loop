# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Request Info with SequentialBuilder

This sample demonstrates using the `.with_request_info()` method to pause a
SequentialBuilder workflow BEFORE a selected agent runs, allowing external input
(e.g., human steering) before the agent responds.

Purpose:
Show how to use the request info API that pauses before selected agent responses,
using the standard request_info pattern for consistency.

Demonstrate:
- Configuring request info with `.with_request_info(agents=[...])`
- Handling WorkflowEvent with `event.type == "request_info"`
- Injecting responses back into the workflow via `workflow.run(responses=..., stream=True)`

Prerequisites:
- Azure OpenAI configured with required environment variables
- Authentication via azure-identity (run az login before executing)
"""

import asyncio
import logging
import os

from agent_framework import (
    AgentExecutorResponse,
    Message,
    WorkflowEvent,
    WorkflowRunState,
)
from agent_framework_orchestrations import AgentRequestInfoResponse, SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from agent_framework_openai import OpenAIChatCompletionClient


load_dotenv()

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s  %(message)s")
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

    # Create agents for a sequential document review workflow
    drafter = chat_client.as_agent(
        name="drafter",
        instructions=("You are a document drafter. When given a topic, create a brief draft (2-3 sentences)."),
    )

    editor = chat_client.as_agent(
        name="editor",
        instructions=(
            "You are an editor. Review the draft and suggest improvements. "
            "Incorporate any human feedback that was provided."
        ),
    )

    finalizer = chat_client.as_agent(
        name="finalizer",
        instructions=(
            "You are a finalizer. Take the edited content and create a polished final version. "
            "Incorporate any additional feedback provided."
        ),
    )

    # Build workflow with request info enabled for editor only.
    workflow = (
        SequentialBuilder(participants=[drafter, editor, finalizer])
        .with_request_info(agents=["editor"])
        .build()
    )

    # Run the workflow with request info handling
    pending_responses: dict[str, AgentRequestInfoResponse] | None = None
    workflow_complete = False
    output_chunks: list[str] = []

    logger.info("Starting document review workflow")

    while not workflow_complete:
        # Run or continue the workflow
        stream = (
            workflow.run(responses=pending_responses, stream=True)
            if pending_responses
            else workflow.run("Write a brief introduction to artificial intelligence.", stream=True)
        )

        pending_responses = None

        # Process events
        async for event in stream:
            if isinstance(event, WorkflowEvent) and event.type == "request_info":
                if isinstance(event.data, AgentExecutorResponse):
                    # Display context and latest response for steering.
                    logger.info(
                        "REQUEST INFO: agent %s responded: %s",
                        event.source_executor_id,
                        event.data.agent_response.text,
                    )
                    if event.data.full_conversation:
                        print("Conversation context:")
                        recent = (
                            event.data.full_conversation[-2:]
                            if len(event.data.full_conversation) > 2
                            else event.data.full_conversation
                        )
                        for msg in recent:
                            role_name = msg.role.value if hasattr(msg.role, "value") and not isinstance(msg.role, str) else msg.role
                            name = msg.author_name or role_name
                            text = (msg.text or "")[:150]
                            logger.debug("  [%s]: %s...", name, text)
                        print("-" * 40)

                    # Get feedback on the agent's response (approve or request iteration)
                    user_input = input("Your guidance (or 'skip' to approve): ")  # noqa: ASYNC250
                    if user_input.lower() == "skip":
                        user_input = AgentRequestInfoResponse.approve()
                    else:
                        user_input = AgentRequestInfoResponse.from_strings([user_input])

                    pending_responses = {event.request_id: user_input}
                    logger.info("Resuming workflow")

            elif isinstance(event, WorkflowEvent) and event.type == "output":
                if event.data:
                    if isinstance(event.data, list):
                        for msg in event.data:
                            if msg.text:
                                output_chunks.append(str(msg.text))
                    else:
                        output_chunks.append(str(event.data))

            elif isinstance(event, WorkflowEvent) and event.type == "status" and event.state == WorkflowRunState.IDLE:
                logger.info("WORKFLOW COMPLETE")
                final_output = "".join(output_chunks).strip()
                logger.info("Final output: %s", final_output if final_output else "(no output)")
                workflow_complete = True


if __name__ == "__main__":
    asyncio.run(main())

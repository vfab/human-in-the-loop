# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Request Info with Sequential Workflow (Group Chat Style)

This sample demonstrates using the `.with_request_info()` method to pause a
sequential workflow before specific agents speak, allowing human input to steer
their response.

Purpose:
Show how to use the request info API with selective filtering to pause before
specific participants speak, allowing human input to steer their response.

Demonstrate:
- Configuring request info with `.with_request_info(agents=[...])`
- Using agent filtering to reduce interruptions
- Steering agent behavior with pre-agent human input

Prerequisites:
- Azure OpenAI configured with required environment variables
- Authentication via azure-identity (run az login before executing)
"""

import asyncio
import logging
import os
from typing import Any

from agent_framework import (
    AgentExecutorResponse,
    WorkflowEvent,
    WorkflowRunState,
)
from azure.identity import AzureCliCredential
from agent_framework_orchestrations import AgentRequestInfoResponse, SequentialBuilder
from dotenv import load_dotenv
from agent_framework_openai import OpenAIChatCompletionClient
from email_delivery import resolve_email_recipient, send_email_via_acs

load_dotenv()

logger = logging.getLogger(__name__)

# Store chat client at module level for email functions to access config
_chat_client: OpenAIChatCompletionClient | None = None


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read attribute if present, otherwise return default."""
    return getattr(obj, name, default)


def _normalize_summary_lines(conversation_messages: list[Any], streamed_updates: list[str]) -> list[str]:
    """Build summary lines from the richest available source."""
    lines: list[str] = []

    if conversation_messages:
        for msg in conversation_messages:
            text = (_safe_attr(msg, "text", "") or "").strip()
            if not text:
                continue
            role = _safe_attr(_safe_attr(msg, "role", "unknown"), "value", _safe_attr(msg, "role", "unknown"))
            name = _safe_attr(msg, "author_name", None) or str(role)
            lines.append(f"[{name}]: {text}")

    if not lines:
        lines.extend([line for line in streamed_updates if line.strip()])

    return lines


def _resolve_email_recipient() -> tuple[str, str]:
    return resolve_email_recipient()


def send_summary_email_via_smtp(summary: str) -> str:
    """Send the workflow summary to the configured recipient via Azure Communication Services Email."""
    recipient, recipient_source = _resolve_email_recipient()
    logger.info("Sending email to: %s (%s)", recipient, recipient_source)
    send_email_via_acs(
        subject="Group Discussion Summary - AI Tools Adoption",
        body=summary,
        recipient=recipient,
    )
    return recipient


def request_email_send_approval(summary: str, recipient: str) -> bool:
    """Ask for explicit human approval before sending summary email."""
    print("\n" + "=" * 60)
    print("EMAIL SEND APPROVAL REQUIRED")
    print("=" * 60)
    print(f"The following summary will be emailed to: {recipient}\n")
    print(summary)
    print("\nApprove sending email? [y/N]")
    choice = input("Choice: ").strip().lower()  # noqa: ASYNC250
    return choice in {"y", "yes"}


async def main() -> None:
    global _chat_client
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s  %(message)s")

    # Pin a known-supported Azure OpenAI API version
    api_version = "2024-12-01-preview"

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    model = os.getenv("AZURE_OPENAI_CHAT_MODEL") or os.getenv("AZURE_OPENAI_MODEL")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if not endpoint or not model:
        raise ValueError(
            "Missing Azure OpenAI config. Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_MODEL (or AZURE_OPENAI_MODEL)."
        )

    if api_key:
        _chat_client = OpenAIChatCompletionClient(
            model=model,
            azure_endpoint=endpoint,
            api_version=api_version,
            api_key=api_key,
        )
    else:
        _chat_client = OpenAIChatCompletionClient(
            model=model,
            azure_endpoint=endpoint,
            api_version=api_version,
            credential=AzureCliCredential(),
        )

    # Create agents for team discussion
    optimist = _chat_client.as_agent(
        name="optimist",
        instructions=(
            "You are an optimistic team member discussing AI tool adoption. You see opportunities and potential. "
            "Respond constructively, building on others' points while maintaining a positive outlook. "
            "Keep your response to 2-3 sentences."
        ),
    )

    pragmatist = _chat_client.as_agent(
        name="pragmatist",
        instructions=(
            "You are a pragmatic team member. You focus on practical implementation and realistic timelines. "
            "Sometimes you respectfully disagree with overly optimistic views with concrete reasoning. "
            "Keep your response to 2-3 sentences."
        ),
    )

    creative = _chat_client.as_agent(
        name="creative",
        instructions=(
            "You are a creative team member. You propose innovative solutions and think outside the box. "
            "Offer alternative approaches that might not be conventional but are worth considering. "
            "Keep your response to 2-3 sentences."
        ),
    )

    # Build sequential workflow with request info enabled for pragmatist
    # This allows human steering before pragmatist's response
    workflow = (
        SequentialBuilder(participants=[optimist, pragmatist, creative])
        .with_request_info(agents=["pragmatist"])
        .build()
    )

    # Run the workflow with human-in-the-loop
    pending_responses: dict[str, AgentRequestInfoResponse] | None = None
    workflow_complete = False
    email_handled = False
    full_conversation: list = []  # Collect conversation from events
    streamed_updates: list[str] = []

    logger.info("Starting group discussion workflow")

    while not workflow_complete:
        # Run or continue the workflow
        stream = (
            workflow.run(responses=pending_responses, stream=True)
            if pending_responses
            else workflow.run(
                "Discuss how our team should approach adopting AI tools for productivity. "
                "Consider benefits, risks, and implementation strategies.",
                stream=True,
            )
        )

        pending_responses = None

        # Process events
        async for event in stream:
            if isinstance(event, WorkflowEvent) and event.type == "request_info":
                if isinstance(event.data, AgentExecutorResponse):
                    # Capture conversation for later summary
                    if event.data.full_conversation:
                        full_conversation = event.data.full_conversation
                    
                    logger.info("INPUT REQUESTED: about to call agent: %s", event.source_executor_id)
                    if event.data.full_conversation:
                        recent = (
                            event.data.full_conversation[-2:]
                            if len(event.data.full_conversation) > 2
                            else event.data.full_conversation
                        )
                        for msg in recent:
                            role_name = _safe_attr(_safe_attr(msg, "role", "unknown"), "value", _safe_attr(msg, "role", "unknown"))
                            name = msg.author_name or role_name
                            text = (msg.text or "")[:150]
                            logger.debug("  [%s]: %s...", name, text)

                    # Get human input to steer the agent
                    user_input = input(f"Feedback for {event.source_executor_id} (or 'skip' to approve): ")  # noqa: ASYNC250
                    if user_input.lower() == "skip":
                        user_input = AgentRequestInfoResponse.approve()
                    else:
                        user_input = AgentRequestInfoResponse.from_strings([user_input])

                    pending_responses = {event.request_id: user_input}
                    logger.info("Resuming discussion")

            elif isinstance(event, WorkflowEvent) and event.type == "output":
                # Capture streaming output updates if the workflow returns incremental chunks.
                text = (_safe_attr(event.data, "text", "") or "").strip()
                if text:
                    author = _safe_attr(event.data, "author_name", None) or "assistant"
                    streamed_updates.append(f"[{author}]: {text}")

            elif isinstance(event, WorkflowEvent) and event.type == "status" and event.state == WorkflowRunState.IDLE:
                if email_handled:
                    workflow_complete = True
                    continue

                logger.info("DISCUSSION COMPLETE")

                summary_lines = _normalize_summary_lines(full_conversation, streamed_updates)
                summary_text = "\n".join(summary_lines).strip()

                if not summary_text:
                    logger.warning("No output captured from workflow. Email not sent.")
                    email_handled = True
                    workflow_complete = True
                    continue

                logger.info("Final conversation:\n%s", summary_text)

                recipient, _ = _resolve_email_recipient()
                if request_email_send_approval(summary_text, recipient):
                    recipient = send_summary_email_via_smtp(summary_text)
                    logger.info("Summary email sent to: %s", recipient)
                else:
                    logger.info("Email send rejected by human reviewer.")

                email_handled = True
                workflow_complete = True


if __name__ == "__main__":
    asyncio.run(main())

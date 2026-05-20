# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Request Info with ConcurrentBuilder

This sample demonstrates using the `.with_request_info()` method to pause a
ConcurrentBuilder workflow for specific agents, allowing human review and
modification of individual agent outputs before aggregation.

Purpose:
Show how to use the request info API that pauses for selected concurrent agents,
allowing review and steering of their results.

Demonstrate:
- Configuring request info with `.with_request_info()` for specific agents
- Reviewing output from individual agents during concurrent execution
- Injecting human guidance for specific agents before aggregation

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables
- Authentication via azure-identity (run az login before executing)
"""

import asyncio
import logging
import os
from typing import Any

from agent_framework import (
    AgentExecutorResponse,
    Message,
    WorkflowEvent,
    WorkflowRunState,
)
from azure.identity import AzureCliCredential
from agent_framework_orchestrations import AgentRequestInfoResponse, ConcurrentBuilder
from dotenv import load_dotenv
from agent_framework_openai import OpenAIChatCompletionClient
from email_delivery import resolve_email_recipient, send_email_via_acs

load_dotenv()

logger = logging.getLogger(__name__)

# Store chat client at module level for aggregator access
_chat_client: OpenAIChatCompletionClient | None = None


def _role_to_text(role: Any) -> str:
    """Normalize role values that may be enums or plain strings."""
    value = getattr(role, "value", role)
    return str(value).lower() if value is not None else ""


def _resolve_email_recipient() -> tuple[str, str]:
    return resolve_email_recipient()


def send_summary_email_via_smtp(summary: str) -> str:
    """Send the workflow summary to the configured recipient via Azure Communication Services Email."""
    recipient, recipient_source = _resolve_email_recipient()
    logger.info("Sending email to: %s (%s)", recipient, recipient_source)
    send_email_via_acs(
        subject="LLM Impact Analysis - Concurrent HITL Summary",
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


async def aggregate_with_synthesis(results: list[AgentExecutorResponse]) -> Any:
    """Custom aggregator that synthesizes concurrent agent outputs using an LLM.

    This aggregator extracts the outputs from each parallel agent and uses the
    chat client to create a unified summary, incorporating any human feedback
    that was injected into the conversation.

    Args:
        results: List of responses from all concurrent agents

    Returns:
        The synthesized summary text
    """
    if not _chat_client:
        return "Error: Chat client not initialized"

    # Extract each agent's final output
    expert_sections: list[str] = []
    human_guidance = ""

    for r in results:
        try:
            messages = getattr(r.agent_response, "messages", [])
            final_text = messages[-1].text if messages and hasattr(messages[-1], "text") else "(no content)"
            expert_sections.append(f"{getattr(r, 'executor_id', 'analyst')}:\n{final_text}")

            # Check for human feedback in the conversation (will be last user message if present)
            if r.full_conversation:
                for msg in reversed(r.full_conversation):
                    if _role_to_text(getattr(msg, "role", "")) == "user" and msg.text and "perspectives" not in msg.text.lower():
                        human_guidance = msg.text
                        break
        except Exception:
            expert_sections.append(f"{getattr(r, 'executor_id', 'analyst')}: (error extracting output)")

    # Build prompt with human guidance if provided
    guidance_text = f"\n\nHuman guidance: {human_guidance}" if human_guidance else ""

    system_msg = Message(
        "system",
        [
            "You are a synthesis expert. Consolidate the following analyst perspectives "
            "into one cohesive, balanced summary (3-4 sentences). If human guidance is provided, "
            "prioritize aspects as directed."
        ],
    )
    user_msg = Message("user", ["\n\n".join(expert_sections) + guidance_text])

    response = await _chat_client.get_response([system_msg, user_msg])
    return response.messages[-1].text if response.messages else ""


async def main() -> None:
    global _chat_client
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s  %(message)s")

    # Pin a known-supported Azure OpenAI API version so the sample does not inherit
    # a stale or unsupported value from the environment.
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

    # Create agents that analyze from different perspectives
    technical_analyst = _chat_client.as_agent(
        name="technical_analyst",
        instructions=(
            "You are a technical analyst. When given a topic, provide a technical "
            "perspective focusing on implementation details, performance, and architecture. "
            "Keep your analysis to 2-3 sentences."
        ),
    )

    business_analyst = _chat_client.as_agent(
        name="business_analyst",
        instructions=(
            "You are a business analyst. When given a topic, provide a business "
            "perspective focusing on ROI, market impact, and strategic value. "
            "Keep your analysis to 2-3 sentences."
        ),
    )

    user_experience_analyst = _chat_client.as_agent(
        name="ux_analyst",
        instructions=(
            "You are a UX analyst. When given a topic, provide a user experience "
            "perspective focusing on usability, accessibility, and user satisfaction. "
            "Keep your analysis to 2-3 sentences."
        ),
    )

    # Build workflow with request info enabled and custom aggregator
    workflow = (
        ConcurrentBuilder(participants=[technical_analyst, business_analyst, user_experience_analyst])
        .with_aggregator(aggregate_with_synthesis)
        # Only enable request info for the technical analyst agent
        .with_request_info(agents=["technical_analyst"])
        .build()
    )

    # Run the workflow with human-in-the-loop
    pending_responses: dict[str, AgentRequestInfoResponse] | None = None
    workflow_complete = False

    logger.info("Starting multi-perspective analysis workflow")

    while not workflow_complete:
        # Run or continue the workflow
        stream = (
            workflow.run(responses=pending_responses, stream=True)
            if pending_responses
            else workflow.run(
                "Analyze the impact of large language models on software development.",
                stream=True,
            )
        )

        pending_responses = None

        # Process events
        async for event in stream:
            if isinstance(event, WorkflowEvent) and event.type == "request_info":
                if isinstance(event.data, AgentExecutorResponse):
                    # Display agent output for review and potential modification
                    logger.info(
                        "INPUT REQUESTED: agent %s responded: %s",
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
                            role_name = msg.role.value if hasattr(msg.role, "value") else msg.role
                            name = msg.author_name or role_name
                            text = (msg.text or "")[:150]
                            logger.debug("  [%s]: %s...", name, text)
                        print("-" * 40)

                    # Get human input to steer this agent's contribution
                    user_input = input("Your guidance for the analysts (or 'skip' to approve): ")  # noqa: ASYNC250
                    if user_input.lower() == "skip":
                        user_input = AgentRequestInfoResponse.approve()
                    else:
                        user_input = AgentRequestInfoResponse.from_strings([user_input])

                    pending_responses = {event.request_id: user_input}
                    logger.info("Resuming workflow")

            elif isinstance(event, WorkflowEvent) and event.type == "output":
                logger.info("WORKFLOW COMPLETE")
                # Custom aggregator returns a string
                if event.data:
                    logger.info("Aggregated output: %s", event.data)
                    summary_text = str(event.data)
                    recipient, _ = _resolve_email_recipient()
                    if request_email_send_approval(summary_text, recipient):
                        recipient = send_summary_email_via_smtp(summary_text)
                        logger.info("Summary email sent to: %s", recipient)
                    else:
                        logger.info("Email send rejected by human reviewer.")
                workflow_complete = True

            elif isinstance(event, WorkflowEvent) and event.type == "status" and event.state == WorkflowRunState.IDLE:
                workflow_complete = True


if __name__ == "__main__":
    asyncio.run(main())

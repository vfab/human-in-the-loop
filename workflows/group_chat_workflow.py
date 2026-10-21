# Copyright (c) Microsoft. All rights reserved.

"""
Group Chat Workflow - Team discussion with human steering.

Extracted from: group_chat_request_info.py

This workflow demonstrates a sequential team discussion where three agents
(optimist, pragmatist, creative) discuss a topic with human-in-the-loop
steering before the pragmatist speaks, followed by an in-app approval of the
whole discussion. Nothing is emailed.

Flow:
1. Optimist kicks off the discussion
2. Pragmatist responds (with human steering opportunity)
3. Creative provides alternative perspective
4. The human accepts or rejects the overall discussion
"""

import logging
from typing import Any, AsyncIterator, Optional

from agent_framework import (
    WorkflowEvent,
    WorkflowRunState,
)
from agent_framework._workflows._agent_executor import AgentExecutorResponse
from agent_framework_orchestrations import AgentRequestInfoResponse, SequentialBuilder
from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential

from . import WorkflowConfig, reply_approved, reply_text

logger = logging.getLogger(__name__)

# Display names shown in the dashboard for each group member
MEMBER_LABELS = {
    "optimist": "Optimist",
    "pragmatist": "Pragmatist",
    "creative": "Creative",
}


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read attribute if present, otherwise return default."""
    return getattr(obj, name, default)


async def run_group_chat_workflow(
    config: WorkflowConfig,
    topic: str = "Discuss how our team should approach adopting AI tools for productivity."
) -> AsyncIterator[WorkflowEvent]:
    """Run the group chat workflow.
    
    Demonstrates sequential team discussion with human steering
    before the pragmatist's response, then an in-app approval of the discussion.
    No email is sent.
    
    Args:
        config: WorkflowConfig with Azure OpenAI settings
        topic: Discussion topic
        
    Yields:
        WorkflowEvent objects for dashboard consumption
    """
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
        
        logger.info("Starting group chat workflow")
        
        # Create agents for team discussion
        optimist = chat_client.as_agent(
            name="optimist",
            instructions=(
                "You are an optimistic team member discussing AI tool adoption. You see opportunities and potential. "
                "Respond constructively, building on others' points while maintaining a positive outlook. "
                "Keep your response to 2-3 sentences."
            ),
        )
        
        pragmatist = chat_client.as_agent(
            name="pragmatist",
            instructions=(
                "You are a pragmatic team member. You focus on practical implementation and realistic timelines. "
                "Sometimes you respectfully disagree with overly optimistic views with concrete reasoning. "
                "Keep your response to 2-3 sentences."
            ),
        )
        
        creative = chat_client.as_agent(
            name="creative",
            instructions=(
                "You are a creative team member. You propose innovative solutions and think outside the box. "
                "Offer alternative approaches that might not be conventional but are worth considering. "
                "Keep your response to 2-3 sentences."
            ),
        )
        
        # Build workflow with request info for pragmatist only
        workflow = (
            SequentialBuilder(participants=[optimist, pragmatist, creative])
            .with_request_info(agents=["pragmatist"])
            .build()
        )
        
        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"Starting group discussion: {topic}"},
            source_executor_id="system"
        )
        
        # Run workflow with human-in-the-loop
        pending_responses: Optional[dict[str, AgentRequestInfoResponse]] = None
        workflow_complete = False
        full_conversation: list[Any] = []
        transcript: dict[str, str] = {}  # member -> latest reply, in speaking order
        steered = False
        summary_text = ""
        
        while not workflow_complete:
            # Run or continue workflow
            stream = (
                workflow.run(responses=pending_responses, stream=True)
                if pending_responses
                else workflow.run(topic, stream=True)
            )
            
            pending_responses = None
            
            # Process events
            async for event in stream:
                if isinstance(event, WorkflowEvent) and event.type == "request_info":
                    if isinstance(event.data, AgentExecutorResponse):
                        agent_response = event.data.agent_response.text
                        full_conversation.extend(
                            getattr(event.data, "full_conversation", [])
                        )
                        
                        # Display pragmatist's response for steering
                        transcript["pragmatist"] = agent_response
                        yield WorkflowEvent(
                            type="agent_message",
                            data={
                                "agent": MEMBER_LABELS.get(event.source_executor_id, event.source_executor_id),
                                "content": agent_response
                            },
                            source_executor_id=event.source_executor_id
                        )
                        
                        # Single steering checkpoint: after one round of guidance the revised
                        # reply is accepted without asking again.
                        guidance = ""
                        if not steered:
                            steered = True
                            reply = yield WorkflowEvent(
                                type="input_required",
                                data={
                                    "request_id": event.request_id,
                                    "prompt": "Give guidance to have the pragmatist revise, or leave blank to continue:",
                                    "agent": "pragmatist"
                                },
                                source_executor_id="system"
                            )
                            guidance = reply_text(reply)
                        
                        if guidance:
                            yield WorkflowEvent(
                                type="agent_message",
                                data={"agent": "you", "content": guidance},
                                source_executor_id="you"
                            )
                        pending_responses = {
                            event.request_id: (
                                AgentRequestInfoResponse.from_strings([guidance])
                                if guidance
                                else AgentRequestInfoResponse.approve()
                            )
                        }
                
                elif (
                    isinstance(event, WorkflowEvent)
                    and event.type == "executor_completed"
                    and isinstance(event.data, list)
                ):
                    # Each member's finished reply arrives here (only the last speaker is
                    # streamed as "output"). The pragmatist is shown at its steering prompt.
                    for item in event.data:
                        if not isinstance(item, AgentExecutorResponse):
                            continue
                        member = item.executor_id
                        text = (item.agent_response.text or "").strip()
                        if not text:
                            continue
                        transcript[member] = text
                        if member != "pragmatist":
                            yield WorkflowEvent(
                                type="agent_message",
                                data={"agent": MEMBER_LABELS.get(member, member), "content": text},
                                source_executor_id=member
                            )
                
                elif isinstance(event, WorkflowEvent) and event.type == "output":
                    # The final speaker streams its reply in tiny chunks; the complete
                    # text is handled via executor_completed, so just note we are done.
                    workflow_complete = True
                
                elif isinstance(event, WorkflowEvent) and event.type == "status":
                    if event.state == WorkflowRunState.IDLE:
                        workflow_complete = True
            
            if workflow_complete and transcript:
                summary_text = "\n\n".join(
                    f"{MEMBER_LABELS.get(member, member)}: {text}"
                    for member, text in transcript.items()
                )
                logger.info("Group discussion complete")
                
                # One in-app approval for the whole discussion
                reply = yield WorkflowEvent(
                    type="approval_required",
                    data={
                        "request_id": "discussion_review",
                        "prompt": "Accept this discussion?",
                        "content": summary_text
                    },
                    source_executor_id="system"
                )
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={"content": (
                        "✓ Discussion accepted" if reply_approved(reply)
                        else "✗ Discussion rejected"
                    )},
                    source_executor_id="system"
                )
        
        yield WorkflowEvent(
            type="workflow_complete",
            data={
                "status": "completed",
                "summary": summary_text,
            },
            source_executor_id="system"
        )
    
    except Exception as e:
        logger.exception("Error in group chat workflow: %s", e)
        yield WorkflowEvent(
            type="error",
            data={"message": str(e)},
            source_executor_id="system"
        )

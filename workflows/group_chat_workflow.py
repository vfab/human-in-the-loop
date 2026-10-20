# Copyright (c) Microsoft. All rights reserved.

"""
Group Chat Workflow - Team discussion with human steering.

Extracted from: group_chat_request_info.py

This workflow demonstrates a sequential team discussion where three agents
(optimist, pragmatist, creative) discuss a topic with human-in-the-loop
steering before the pragmatist speaks, followed by email delivery of the
discussion summary.

Flow:
1. Optimist kicks off the discussion
2. Pragmatist responds (with human steering opportunity)
3. Creative provides alternative perspective
4. Discussion is synthesized and emailed with approval
"""

import logging
import smtplib
from email.message import EmailMessage
from typing import Any, AsyncIterator, Optional

from agent_framework import (
    WorkflowEvent,
    WorkflowRunState,
)
from agent_framework._workflows._agent_executor import AgentExecutorResponse
from agent_framework_orchestrations import AgentRequestInfoResponse, SequentialBuilder
from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential

from . import WorkflowConfig

logger = logging.getLogger(__name__)


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read attribute if present, otherwise return default."""
    return getattr(obj, name, default)


def _resolve_email_recipient(config: WorkflowConfig) -> tuple[str, str]:
    """Resolve the email recipient from configuration."""
    if config.email_recipient:
        return config.email_recipient, "configured EMAIL_RECIPIENT"
    
    if config.smtp_user:
        return config.smtp_user, "SMTP_USER fallback"
    
    raise ValueError("Missing recipient config. Set EMAIL_RECIPIENT or SMTP_USER.")


def send_summary_email_via_smtp(config: WorkflowConfig, summary: str) -> str:
    """Send the discussion summary via SMTP."""
    recipient, recipient_source = _resolve_email_recipient(config)
    
    if not config.smtp_user or not config.smtp_password:
        raise ValueError("Missing SMTP auth. Set SMTP_USER and SMTP_PASSWORD.")
    
    logger.info("Sending email to: %s (%s)", recipient, recipient_source)
    
    message = EmailMessage()
    message["From"] = config.smtp_user
    message["To"] = recipient
    message["Subject"] = "Group Discussion Summary - AI Tools Adoption"
    message.set_content(summary)
    
    smtp_host = config.smtp_host or "smtp.gmail.com"
    smtp_port = config.smtp_port or 465
    
    with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(message)
    
    return recipient


async def run_group_chat_workflow(
    config: WorkflowConfig,
    topic: str = "Discuss how our team should approach adopting AI tools for productivity."
) -> AsyncIterator[WorkflowEvent]:
    """Run the group chat workflow.
    
    Demonstrates sequential team discussion with human steering
    before the pragmatist's response, followed by email delivery.
    
    Args:
        config: WorkflowConfig with Azure OpenAI and SMTP settings
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
                        yield WorkflowEvent(
                            type="agent_message",
                            data={
                                "agent": event.source_executor_id,
                                "content": agent_response
                            },
                            source_executor_id=event.source_executor_id
                        )
                        
                        # Request human steering input
                        yield WorkflowEvent(
                            type="input_required",
                            data={
                                "request_id": event.request_id,
                                "prompt": "Provide guidance to steer the pragmatist (or enter to skip):",
                                "agent": "pragmatist"
                            },
                            source_executor_id="system"
                        )
                        
                        # Default: approve without steering
                        pending_responses = {
                            event.request_id: AgentRequestInfoResponse.approve()
                        }
                
                elif isinstance(event, WorkflowEvent) and event.type == "output":
                    logger.info("Group discussion complete")
                    if event.data:
                        summary_text = str(event.data)
                        yield WorkflowEvent(
                            type="agent_message",
                            data={"content": f"Discussion Summary:\n{summary_text}"},
                            source_executor_id="system"
                        )
                        
                        # Request approval to send email
                        recipient, _ = _resolve_email_recipient(config)
                        yield WorkflowEvent(
                            type="approval_required",
                            data={
                                "request_id": "email_send",
                                "prompt": f"Send this summary via email to {recipient}?",
                                "content": summary_text
                            },
                            source_executor_id="system"
                        )
                    
                    workflow_complete = True
                
                elif isinstance(event, WorkflowEvent) and event.type == "status":
                    if event.state == WorkflowRunState.IDLE:
                        workflow_complete = True
        
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

# Copyright (c) Microsoft. All rights reserved.

"""
Concurrent Request Workflow - Multi-perspective analysis with human approval.

Extracted from: concurrent_request_info.py

This workflow demonstrates concurrent orchestration where multiple agents
(technical analyst, business analyst, UX analyst) analyze a topic in parallel,
with human-in-the-loop approval for the final synthesized summary before
sending as an email.

Flow:
1. Three agents analyze a topic concurrently from different perspectives
2. A custom aggregator synthesizes their outputs using an LLM
3. Human approval is requested before sending the summary via email
4. Summary is sent if approved, otherwise discarded
"""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, AsyncIterator, Optional

from agent_framework import (
    Message,
    WorkflowEvent,
    WorkflowRunState,
)
from agent_framework._workflows._agent_executor import AgentExecutorResponse
from agent_framework_orchestrations import AgentRequestInfoResponse, ConcurrentBuilder
from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential

from . import WorkflowConfig

logger = logging.getLogger(__name__)


@dataclass
class ConcurrentWorkflowState:
    """Track state during workflow execution."""
    chat_client: Optional[OpenAIChatCompletionClient] = None
    email_sent: bool = False
    workflow_complete: bool = False
    pending_responses: Optional[dict[str, AgentRequestInfoResponse]] = None


def _resolve_email_recipient(config: WorkflowConfig) -> tuple[str, str]:
    """Resolve the email recipient from configuration.
    
    Args:
        config: WorkflowConfig with email settings
        
    Returns:
        Tuple of (recipient_email, source_description)
        
    Raises:
        ValueError: If no recipient is configured
    """
    if config.email_recipient:
        return config.email_recipient, "configured EMAIL_RECIPIENT"
    
    if config.smtp_user:
        return config.smtp_user, "SMTP_USER fallback"
    
    raise ValueError(
        "Missing recipient config. Set EMAIL_RECIPIENT or SMTP_USER in environment."
    )


def send_summary_email_via_smtp(config: WorkflowConfig, summary: str) -> str:
    """Send the workflow summary via SMTP.
    
    Args:
        config: WorkflowConfig with SMTP settings
        summary: Summary text to send
        
    Returns:
        Recipient email address used for delivery
        
    Raises:
        ValueError: If SMTP configuration is incomplete
    """
    recipient, recipient_source = _resolve_email_recipient(config)
    
    if not config.smtp_user or not config.smtp_password:
        raise ValueError(
            "Missing SMTP auth. Set SMTP_USER and SMTP_PASSWORD (or GMAIL_SMTP_APP_PASSWORD)."
        )
    
    logger.info("Sending email to: %s (%s)", recipient, recipient_source)
    
    message = EmailMessage()
    message["From"] = config.smtp_user
    message["To"] = recipient
    message["Subject"] = "LLM Impact Analysis - Concurrent HITL Summary"
    message.set_content(summary)
    
    # Note: Gmail SMTP credentials use app-specific passwords
    smtp_host = config.smtp_host or "smtp.gmail.com"
    smtp_port = config.smtp_port or 465
    
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
            smtp.login(config.smtp_user, config.smtp_password)
            smtp.send_message(message)
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        raise
    
    return recipient


async def aggregate_with_synthesis(
    chat_client: OpenAIChatCompletionClient,
    results: list[AgentExecutorResponse]
) -> str:
    """Synthesize concurrent agent outputs using an LLM.
    
    Extracts each agent's output and uses the chat client to create
    a unified summary incorporating any human feedback.
    
    Args:
        chat_client: OpenAI chat client for synthesis
        results: List of responses from all concurrent agents
        
    Returns:
        The synthesized summary text
    """
    # Extract each agent's final output
    expert_sections: list[str] = []
    human_guidance = ""
    
    for r in results:
        try:
            messages = getattr(r.agent_response, "messages", [])
            final_text = (
                messages[-1].text 
                if messages and hasattr(messages[-1], "text") 
                else "(no content)"
            )
            executor_id = getattr(r, "executor_id", "analyst")
            expert_sections.append(f"{executor_id}:\n{final_text}")
            
            # Check for human feedback in conversation
            if r.full_conversation:
                for msg in reversed(r.full_conversation):
                    if (msg.role == "user" and msg.text 
                        and "perspectives" not in msg.text.lower()):
                        human_guidance = msg.text
                        break
        except Exception as e:
            executor_id = getattr(r, "executor_id", "analyst")
            expert_sections.append(f"{executor_id}: (error extracting output: {e})")
    
    # Build prompt with human guidance
    guidance_text = (
        f"\n\nHuman guidance: {human_guidance}" 
        if human_guidance 
        else ""
    )
    
    system_msg = Message(
        "system",
        [
            "You are a synthesis expert. Consolidate the following analyst perspectives "
            "into one cohesive, balanced summary (3-4 sentences). If human guidance is provided, "
            "prioritize aspects as directed."
        ],
    )
    user_msg = Message("user", ["\n\n".join(expert_sections) + guidance_text])
    
    response = await chat_client.get_response([system_msg, user_msg])
    return response.messages[-1].text if response.messages else ""


async def run_concurrent_workflow(
    config: WorkflowConfig,
    analysis_topic: str = "Analyze the impact of large language models on software development."
) -> AsyncIterator[WorkflowEvent]:
    """Run the concurrent request workflow.
    
    Demonstrates concurrent orchestration with multi-perspective analysis and
    human-in-the-loop approval for email delivery.
    
    Args:
        config: WorkflowConfig with Azure OpenAI and SMTP settings
        analysis_topic: Topic for the agents to analyze
        
    Yields:
        WorkflowEvent objects for dashboard consumption:
        - agent_message: Agent analysis output
        - request_info: Human approval needed
        - workflow_complete: Workflow finished
        - error: Processing error occurred
    """
    state = ConcurrentWorkflowState()
    
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
            state.chat_client = OpenAIChatCompletionClient(
                model=config.azure_openai_chat_deployment,
                azure_endpoint=config.azure_openai_endpoint,
                api_version=api_version,
                api_key=config.azure_openai_api_key,
            )
        else:
            state.chat_client = OpenAIChatCompletionClient(
                model=config.azure_openai_chat_deployment,
                azure_endpoint=config.azure_openai_endpoint,
                api_version=api_version,
                credential=AzureCliCredential(),
            )
        
        logger.info("Starting concurrent workflow")
        
        # Create agents from different perspectives
        technical_analyst = state.chat_client.as_agent(
            name="technical_analyst",
            instructions=(
                "You are a technical analyst. When given a topic, provide a technical "
                "perspective focusing on implementation details, performance, and architecture. "
                "Keep your analysis to 2-3 sentences."
            ),
        )
        
        business_analyst = state.chat_client.as_agent(
            name="business_analyst",
            instructions=(
                "You are a business analyst. When given a topic, provide a business "
                "perspective focusing on ROI, market impact, and strategic value. "
                "Keep your analysis to 2-3 sentences."
            ),
        )
        
        ux_analyst = state.chat_client.as_agent(
            name="ux_analyst",
            instructions=(
                "You are a UX analyst. When given a topic, provide a user experience "
                "perspective focusing on usability, accessibility, and user satisfaction. "
                "Keep your analysis to 2-3 sentences."
            ),
        )
        
        # Build workflow with request info for technical analyst only
        workflow = (
            ConcurrentBuilder(
                participants=[technical_analyst, business_analyst, ux_analyst]
            )
            .with_aggregator(
                lambda results: aggregate_with_synthesis(state.chat_client, results)
            )
            .with_request_info(agents=["technical_analyst"])
            .build()
        )
        
        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"Starting analysis: {analysis_topic}"},
            source_executor_id="system"
        )
        
        # Run workflow with human-in-the-loop
        state.pending_responses = None
        state.workflow_complete = False
        summary_text = ""
        
        while not state.workflow_complete:
            # Run or continue workflow
            stream = (
                workflow.run(responses=state.pending_responses, stream=True)
                if state.pending_responses
                else workflow.run(analysis_topic, stream=True)
            )
            
            state.pending_responses = None
            
            # Process events
            async for event in stream:
                if isinstance(event, WorkflowEvent) and event.type == "request_info":
                    if isinstance(event.data, AgentExecutorResponse):
                        yield WorkflowEvent(
                            type="agent_message",
                            data={
                                "agent": event.source_executor_id,
                                "content": event.data.agent_response.text
                            },
                            source_executor_id=event.source_executor_id
                        )
                        
                        # Yield approval request
                        yield WorkflowEvent(
                            type="approval_required",
                            data={
                                "request_id": event.request_id,
                                "prompt": f"Approve output from {event.source_executor_id}?",
                                "agent": event.source_executor_id
                            },
                            source_executor_id=event.source_executor_id
                        )
                        
                        # Wait for user response (would come from dashboard)
                        # For now, yield and let caller handle
                        state.pending_responses = {
                            event.request_id: AgentRequestInfoResponse.approve()
                        }
                
                elif isinstance(event, WorkflowEvent) and event.type == "output":
                    # Workflow complete with aggregated output
                    logger.info("Workflow aggregation complete")
                    if event.data:
                        summary_text = str(event.data)
                        yield WorkflowEvent(
                            type="agent_message",
                            data={"content": f"Synthesized Summary:\n{summary_text}"},
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
                    
                    state.workflow_complete = True
                
                elif isinstance(event, WorkflowEvent) and event.type == "status":
                    if event.state == WorkflowRunState.IDLE:
                        state.workflow_complete = True
        
        # Send completion event
        if summary_text:
            yield WorkflowEvent(
                type="workflow_complete",
                data={
                    "status": "completed",
                    "summary": summary_text,
                    "email_sent": state.email_sent
                },
                source_executor_id="system"
            )
        else:
            yield WorkflowEvent(
                type="workflow_complete",
                data={"status": "completed"},
                source_executor_id="system"
            )
    
    except Exception as e:
        logger.exception("Error in concurrent workflow: %s", e)
        yield WorkflowEvent(
            type="error",
            data={"message": str(e), "error_type": type(e).__name__},
            source_executor_id="system"
        )

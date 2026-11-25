# Copyright (c) Microsoft. All rights reserved.

"""
Approval Workflow - Email assistant with human approval.

Extracted from: agents_with_approval_requests.py

This workflow demonstrates an email assistant that processes incoming emails
and generates responses, with human-in-the-loop approval before sending.

Flow:
1. Receive sample emails
2. Preprocess (flag important senders)
3. Agent generates response
4. Human reviews and approves before sending
5. Email sent via SMTP
"""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, AsyncIterator, Optional

from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential
from agent_framework import WorkflowEvent

from . import WorkflowConfig, reply_approved

logger = logging.getLogger(__name__)


@dataclass
class Email:
    """Represents an email message."""
    recipient: str
    sender: str
    subject: str
    body: str
    
    def __str__(self) -> str:
        return f"To: {self.recipient}\nFrom: {self.sender}\nSubject: {self.subject}\n\n{self.body}"


_TEAM = "team@example.com"

DEFAULT_SCENARIO = "default"

# Incoming-email scenarios selectable from the dashboard's sample drop-down.
EMAIL_SCENARIOS: dict[str, list[Email]] = {
    DEFAULT_SCENARIO: [
        Email(_TEAM, "john@example.com", "Project Status Update",
              "Hi, can you provide an update on the current project status?"),
        Email(_TEAM, "sam@example.com", "Urgent: Budget Review",
              "Need your input on the Q4 budget allocation ASAP."),
    ],
    "status_update": [
        Email(_TEAM, "john@example.com", "Project Status Update",
              "Hi, can you provide an update on the current project status?"),
    ],
    "budget_review": [
        Email(_TEAM, "sam@example.com", "Urgent: Budget Review",
              "Need your input on the Q4 budget allocation ASAP."),
    ],
    "meeting_request": [
        Email(_TEAM, "priya@example.com", "Meeting Request",
              "Could we find 30 minutes next week to go over the launch plan? "
              "I'm free Tuesday or Thursday afternoon."),
    ],
    "customer_complaint": [
        Email(_TEAM, "customer@example.com", "Order arrived damaged",
              "My order #48213 arrived with a cracked screen. I'd like a replacement "
              "or a refund as soon as possible."),
    ],
    "invoice_question": [
        Email(_TEAM, "accounting@example.com", "Question about invoice #1042",
              "The total on invoice #1042 looks higher than the quote we agreed on. "
              "Can you explain the difference?"),
    ],
}


def _resolve_email_recipient(config: WorkflowConfig) -> str:
    """Resolve the email recipient from configuration."""
    if config.email_recipient:
        return config.email_recipient
    if config.smtp_user:
        return config.smtp_user
    raise ValueError("Missing recipient config. Set EMAIL_RECIPIENT or SMTP_USER.")


def validate_smtp_config(config: WorkflowConfig) -> None:
    """Validate the configuration shared by outgoing emails."""
    _resolve_email_recipient(config)
    if not config.smtp_user or not config.smtp_password:
        raise ValueError("Missing SMTP auth. Set SMTP_USER and SMTP_PASSWORD.")


def send_smtp_message(config: WorkflowConfig, subject: str, body: str) -> None:
    """Send a message to the configured recipient through SMTP."""
    validate_smtp_config(config)
    recipient = _resolve_email_recipient(config)
    message = EmailMessage()
    message["From"] = config.smtp_user
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    smtp_host = config.smtp_host or "smtp.gmail.com"
    smtp_port = config.smtp_port or 465

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as smtp:
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(message)


def send_email_via_smtp(config: WorkflowConfig, email: Email, body: str) -> None:
    """Send an approved email response through SMTP."""
    send_smtp_message(config, f"Re: {email.subject}", body)


def send_notification_email(
    config: WorkflowConfig,
    workflow_id: str,
    request_kind: str,
    payload: dict[str, Any],
) -> None:
    """Notify the recipient of a pending human interaction."""
    action = "input" if request_kind == "input" else "approval"
    subject = "Human-in-the-loop action required"
    body = (
        f"The {workflow_id} workflow is waiting for your {action}.\n\n"
        "Return to the open dashboard to respond. Keep the page open; "
        "the request expires after five minutes.\n"
    )
    prompt = payload.get("prompt")
    if isinstance(prompt, str) and prompt:
        body += f"\nRequest:\n{prompt}\n"
    output = payload.get("workflow_output")
    if isinstance(output, str) and output:
        body += f"\nWorkflow output:\n{output}\n"
    context = payload.get("email_context")
    if isinstance(context, str) and context:
        body += f"\nWorkflow context:\n{context}\n"
    content = payload.get("content")
    if isinstance(content, str) and content:
        body += f"\nResponse to review:\n{content}\n"
    options = payload.get("options")
    if isinstance(options, list) and all(isinstance(option, str) for option in options) and options:
        body += f"\nOptions: {', '.join(options)}\n"
    if request_kind == "approval_batch":
        if workflow_id == "concurrent":
            subject = "Concurrent workflow: analyst review required"
        sections = [
            f"{item.get('label') or item.get('agent') or 'Analyst'}:\n"
            f"{item.get('content', '')}"
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]
        body += "\nReview each response and approve or reject it in the dashboard:\n\n"
        body += "\n\n".join(sections) + "\n"
    send_smtp_message(
        config,
        subject,
        body,
    )


async def run_approval_workflow(
    config: WorkflowConfig,
    scenario: str = "",
) -> AsyncIterator[WorkflowEvent]:
    """Run the approval workflow.
    
    Demonstrates email assistant with human-in-the-loop approval
    before sending responses.
    
    Args:
        config: WorkflowConfig with Azure OpenAI and SMTP settings
        scenario: Key of the incoming-email scenario in EMAIL_SCENARIOS (blank = default)
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
        
        logger.info("Starting approval workflow")
        
        # Create email assistant agent
        email_agent = chat_client.as_agent(
            name="Email Writer",
            instructions=(
                "You are an excellent email assistant. Your role is to respond to incoming emails. "
                "Be professional, clear, and concise. "
                "Provide thoughtful responses based on the email content."
            ),
        )
        
        # Emails to process (the dashboard's sample drop-down picks the scenario)
        sample_emails = EMAIL_SCENARIOS.get(scenario) or EMAIL_SCENARIOS[DEFAULT_SCENARIO]
        
        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"Processing {len(sample_emails)} email(s)..."},
            source_executor_id="system"
        )
        
        # Process each email
        for i, email in enumerate(sample_emails):
            try:
                # Preprocess: flag important senders
                message = str(email)
                if email.sender == "sam@example.com":
                    message = (
                        "⚠️ IMPORTANT EMAIL FROM KEY TEAM MEMBER ⚠️\n"
                        "This email requires careful attention.\n\n"
                        + message
                    )
                
                logger.info(
                    "Processing email %d/%d - To: %s, From: %s, Subject: %s",
                    i + 1, len(sample_emails),
                    email.recipient, email.sender, email.subject
                )
                
                # Generate response
                response = await email_agent.run(message)
                draft_body = response.text
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={
                        "content": f"Email {i+1}/{len(sample_emails)} from {email.sender}:\n{email.subject}"
                    },
                    source_executor_id="system"
                )
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={
                        "agent": "Email Writer",
                        "content": f"Draft Response:\n{draft_body}"
                    },
                    source_executor_id="Email Writer"
                )
                
                # Request approval; the human's reply comes back from the yield
                reply = yield WorkflowEvent(
                    type="approval_required",
                    data={
                        "request_id": f"email_{i}",
                        "prompt": f"Send this response to {_resolve_email_recipient(config)}?",
                        "subject": f"Re: {email.subject}",
                        "content": draft_body,
                        "email_context": f"Original email:\n{email}",
                    },
                    source_executor_id="system"
                )
                
                if not reply_approved(reply):
                    yield WorkflowEvent(
                        type="agent_message",
                        data={"content": f"✗ Email {i+1} not sent (rejected)"},
                        source_executor_id="system"
                    )
                    continue
                
                try:
                    recipient = _resolve_email_recipient(config)
                    await asyncio.to_thread(send_email_via_smtp, config, email, draft_body)
                    yield WorkflowEvent(
                        type="agent_message",
                        data={
                            "content": f"✓ Email sent to {recipient}"
                        },
                        source_executor_id="system"
                    )
                except Exception as e:
                    logger.error(
                        "Email delivery failed (exception_type=%s)",
                        type(e).__name__,
                    )
                    yield WorkflowEvent(
                        type="error",
                        data={"message": "Email delivery failed."},
                        source_executor_id="system"
                    )
            
            except Exception as e:
                logger.error(
                    "Email workflow item %d failed (exception_type=%s)",
                    i + 1,
                    type(e).__name__,
                )
                yield WorkflowEvent(
                    type="error",
                    data={"message": f"Email workflow item {i + 1} failed."},
                    source_executor_id="system"
                )
        
        yield WorkflowEvent(
            type="workflow_complete",
            data={"status": "completed", "emails_processed": len(sample_emails)},
            source_executor_id="system"
        )
    
    except Exception as e:
        logger.error(
            "Approval workflow failed (exception_type=%s)",
            type(e).__name__,
        )
        yield WorkflowEvent(
            type="error",
            data={"message": "Workflow failed. Check server logs."},
            source_executor_id="system"
        )

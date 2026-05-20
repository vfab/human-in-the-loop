# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Email Assistant Workflow with Human-in-the-Loop Approval

This sample demonstrates a workflow that automatically replies to incoming emails
with human-in-the-loop approval for sensitive operations.

Workflow:
1. Receive incoming email
2. Preprocess email (flag if from important sender)
3. Agent reviews email and gathers context
4. Agent composes response
5. Final response is output

Purpose:
Show how to integrate email processing with an AI agent in a workflow.
"""

import asyncio
import logging
import os
from dataclasses import dataclass

from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from email_delivery import resolve_email_recipient, send_email_via_acs

load_dotenv()

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


class EmailAssistant:
    """Simple email assistant using OpenAI."""

    def __init__(self, chat_client: OpenAIChatCompletionClient):
        """Initialize the email assistant."""
        self.chat_client = chat_client
        self.agent = self._create_agent()

    def _create_agent(self):
        """Create the email writer agent."""
        return self.chat_client.as_agent(
            name="Email Writer",
            instructions=(
                "You are an excellent email assistant. Your role is to respond to incoming emails. "
                "Be professional, clear, and concise. "
                "Provide thoughtful responses based on the email content."
            ),
        )

    async def process_email(self, email: Email) -> str:
        """Process an email and generate a response."""
        # Preprocess: Add flag if sender is important
        message = str(email)
        if email.sender == "sam@example.com":
            message = (
                "⚠️ IMPORTANT EMAIL FROM KEY TEAM MEMBER ⚠️\n"
                "This email requires careful attention.\n\n"
                + message
            )

        # Request response from agent
        logger.info("Processing email - To: %s, From: %s, Subject: %s", email.recipient, email.sender, email.subject)
        logger.info("Sending to AI agent for response...")

        # Get agent response
        response = await self.agent.run(message)
        return response.text


def send_email_via_smtp(email: Email, body: str) -> None:
    """Backward-compatible wrapper that now sends via Azure Communication Services Email."""
    send_email_via_acs(subject=f"Re: {email.subject}", body=body, recipient=email.recipient)


def request_human_approval(email: Email, draft_body: str) -> str | None:
    """Show generated draft and ask for human approval before sending.

    Returns:
        Approved body text, possibly edited, or None if rejected.
    """
    print("\n" + "=" * 70)
    print("HUMAN APPROVAL REQUIRED")
    print("=" * 70)
    print(f"To: {email.recipient}")
    print(f"Subject: Re: {email.subject}\n")
    print("Draft response:\n")
    print(draft_body)
    print("\nOptions: [a]pprove and send, [e]dit then send, [r]eject")

    while True:
        choice = input("Choose a/e/r: ").strip().lower()  # noqa: ASYNC250
        if choice in {"a", "approve"}:
            return draft_body
        if choice in {"e", "edit"}:
            print("Enter your edited response. Finish with a single '.' on its own line.")
            lines: list[str] = []
            while True:
                line = input()  # noqa: ASYNC250
                if line == ".":
                    break
                lines.append(line)
            edited_body = "\n".join(lines).strip()
            if edited_body:
                return edited_body
            print("Edited response was empty. Keeping original draft.")
            return draft_body
        if choice in {"r", "reject"}:
            return None
        print("Invalid choice. Please enter 'a', 'e', or 'r'.")


async def main() -> None:
    """Main function to run the email assistant workflow."""
    print("=" * 70)
    print("EMAIL ASSISTANT WITH HUMAN-IN-THE-LOOP")
    print("=" * 70)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s  %(message)s")
    logger.info("Starting Email Assistant with Human-in-the-Loop")

    # Pin a known-supported Azure OpenAI API version so the sample does not
    # inherit a stale or unsupported value from the environment.
    api_version = "2024-12-01-preview"

    # Initialize Azure OpenAI chat client.
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    model = os.getenv("AZURE_OPENAI_CHAT_MODEL") or os.getenv("AZURE_OPENAI_MODEL")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if not endpoint or not model:
        raise ValueError(
            "Missing Azure OpenAI config. Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_MODEL (or AZURE_OPENAI_MODEL)."
        )

    if api_key:
        # API key auth avoids tenant mismatches when local Azure CLI is signed into a different tenant.
        chat_client = OpenAIChatCompletionClient(
            model=model,
            azure_endpoint=endpoint,
            api_version=api_version,
            api_key=api_key,
        )
    else:
        # Fallback to Entra auth when API key is not configured.
        chat_client = OpenAIChatCompletionClient(
            model=model,
            azure_endpoint=endpoint,
            api_version=api_version,
            credential=AzureCliCredential(),
        )

    # Create email assistant
    assistant = EmailAssistant(chat_client)

    recipient_email, _ = resolve_email_recipient()

    # Create a sample email
    incoming_email = Email(
        recipient=recipient_email,
        sender="sam@example.com",
        subject="Urgent: Agent Framework Review Required",
        body=(
            "Hi Vince,\n\n"
            "Please review the latest agent framework updates and provide your feedback. "
            "This is critical for our Q4 roadmap. "
            "The changes include improvements to error handling and performance optimization.\n\n"
            "Can you review and provide feedback by end of week?\n\n"
            "Thanks,\nSam"
        ),
    )

    # Process the email
    try:
        response = await assistant.process_email(incoming_email)

        approved_body = request_human_approval(incoming_email, response)
        if approved_body is None:
            logger.info("Email send rejected by human reviewer.")
            return

        send_email_via_smtp(incoming_email, approved_body)

        logger.info("EMAIL SENT - Sent to: %s", incoming_email.recipient)

    except Exception as e:
            logger.error("Error processing email: %s", e, exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())

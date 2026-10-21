# Copyright (c) Microsoft. All rights reserved.

"""
Workflows module - Extracted reusable workflow implementations.

This module contains extracted logic from the standalone HITL demo scripts,
refactored as async generators that yield WorkflowEvent objects for
integration with the main FastAPI dashboard.

Each workflow accepts a WorkflowConfig with shared Azure OpenAI and SMTP
credentials, and yields events for the dashboard to display and handle.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class WorkflowConfig:
    """Shared configuration for all workflows.
    
    Contains Azure OpenAI credentials and SMTP settings needed by any workflow.
    """
    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_chat_deployment: str
    azure_openai_api_version: str = "2024-12-01-preview"
    
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    
    email_recipient: str = ""

    @classmethod
    def from_env(cls) -> "WorkflowConfig":
        """Load configuration from environment variables."""
        return cls(
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            azure_openai_chat_deployment=(
                os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
                or os.getenv("AZURE_OPENAI_CHAT_MODEL")
                or ""
            ),
            azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=int(os.getenv("SMTP_PORT", "465")),
            smtp_user=os.getenv("SMTP_USER", ""),
            # Google displays app passwords in groups separated by spaces; strip them.
            smtp_password=(
                os.getenv("SMTP_PASSWORD")
                or os.getenv("GMAIL_SMTP_APP_PASSWORD")
                or ""
            ).replace(" ", ""),
            email_recipient=os.getenv("EMAIL_RECIPIENT", ""),
        )

    def validate(self) -> Optional[str]:
        """Validate required configuration.
        
        Returns:
            Error message if validation fails, None otherwise.
        """
        # API key is optional: workflows fall back to AzureCliCredential (az login).
        if not self.azure_openai_endpoint:
            return "Missing AZURE_OPENAI_ENDPOINT"
        if not self.azure_openai_chat_deployment:
            return "Missing AZURE_OPENAI_CHAT_DEPLOYMENT_NAME or AZURE_OPENAI_CHAT_MODEL"
        return None


__all__ = [
    "WorkflowConfig",
    "reply_approved",
    "reply_text",
]


# Human-in-the-loop protocol: a workflow generator yields an ``approval_required`` or
# ``input_required`` event and receives the human's reply as the result of the ``yield``
# (via ``agen.asend(reply)``). Plain ``async for`` consumers send ``None``.

def reply_approved(reply: Optional[dict], default: bool = False) -> bool:
    """Return whether the human approved. ``default`` applies when no human replied."""
    if reply is None:
        return default
    return bool(reply.get("approved", False))


def reply_text(reply: Optional[dict]) -> str:
    """Return the text the human entered, or an empty string."""
    if reply is None:
        return ""
    return str(reply.get("input") or reply.get("feedback") or "").strip()

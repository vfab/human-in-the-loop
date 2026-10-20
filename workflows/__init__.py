# Copyright (c) Microsoft. All rights reserved.

"""
Workflows module - Extracted reusable workflow implementations.

This module contains extracted logic from the standalone HITL demo scripts,
refactored as async generators that yield WorkflowEvent objects for
integration with the main FastAPI dashboard.

Each workflow accepts a WorkflowConfig with shared Azure OpenAI and SMTP
credentials, and yields events for the dashboard to display and handle.
"""

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
    
    def validate(self) -> Optional[str]:
        """Validate required configuration.
        
        Returns:
            Error message if validation fails, None otherwise.
        """
        if not self.azure_openai_api_key:
            return "Missing AZURE_OPENAI_API_KEY"
        if not self.azure_openai_endpoint:
            return "Missing AZURE_OPENAI_ENDPOINT"
        if not self.azure_openai_chat_deployment:
            return "Missing AZURE_OPENAI_CHAT_DEPLOYMENT_NAME or AZURE_OPENAI_CHAT_MODEL"
        return None


__all__ = [
    "WorkflowConfig",
    # Workflow imports will be added here after extraction
]

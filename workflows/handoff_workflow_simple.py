# Copyright (c) Microsoft. All rights reserved.

"""
Handoff Workflow - Dynamic agent transfer based on context (Simplified Implementation).

This is a simplified proof-of-concept of the handoff orchestration pattern
that works with the current Agent Framework API.

Flow:
1. Customer Service Agent analyzes the request
2. If technical issue detected → handoff to Technical Expert
3. If escalation required → handoff to Product Manager
4. Each agent has full context of previous exchanges
5. No human approval checkpoints (control passes automatically)
"""

import logging
from typing import AsyncIterator

from agent_framework import (
    WorkflowEvent,
)
from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential

from . import WorkflowConfig

logger = logging.getLogger(__name__)

# Handoff routing rules (keywords that trigger escalation)
ESCALATION_KEYWORDS = ["escalate", "manager", "senior", "urgent", "critical"]
TECHNICAL_KEYWORDS = ["technical", "bug", "error", "crash", "api", "integration", "code", "502", "timeout"]
MANAGER_KEYWORDS = ["contract", "billing", "policy", "decision", "executive", "approval"]


def should_escalate_to_technical(message: str) -> bool:
    """Determine if message requires technical expertise."""
    return any(keyword in message.lower() for keyword in TECHNICAL_KEYWORDS)


def should_escalate_to_manager(message: str) -> bool:
    """Determine if message requires management decision."""
    return any(keyword in message.lower() for keyword in MANAGER_KEYWORDS)


def should_escalate_further(message: str) -> bool:
    """Determine if escalation to higher level is needed."""
    return any(keyword in message.lower() for keyword in ESCALATION_KEYWORDS)


async def run_handoff_workflow(
    config: WorkflowConfig,
    topic: str = "I need technical support for my service account."
) -> AsyncIterator[WorkflowEvent]:
    """Run the handoff workflow - simple version.

    Demonstrates handoff orchestration where agents transfer control
    based on predefined rules.

    Args:
        config: WorkflowConfig with Azure OpenAI settings
        topic: Initial customer support request

    Yields:
        WorkflowEvent objects for dashboard consumption
    """
    # Validate configuration
    config_error = config.validate()
    if config_error:
        yield WorkflowEvent(
            type="error",
            data={"content": config_error},
            source_executor_id="system"
        )
        return

    try:
        # Initialize chat client
        if config.azure_openai_api_key:
            chat_client = OpenAIChatCompletionClient(
                model=config.azure_openai_chat_deployment,
                azure_endpoint=config.azure_openai_endpoint,
                api_version=config.azure_openai_api_version,
                api_key=config.azure_openai_api_key,
            )
        else:
            chat_client = OpenAIChatCompletionClient(
                model=config.azure_openai_chat_deployment,
                azure_endpoint=config.azure_openai_endpoint,
                api_version=config.azure_openai_api_version,
                credential=AzureCliCredential(),
            )

        logger.info("Starting handoff workflow with topic: %s", topic[:100])

        # Initial message from user
        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"Customer: {topic}"},
            source_executor_id="customer",
        )

        # Phase 1: Customer Service Agent handles initial request
        logger.info("Phase 1: Customer Service Agent")
        yield WorkflowEvent(
            type="agent_message",
            data={"content": "[Agent] Customer Service Agent is reviewing your request..."},
            source_executor_id="system",
        )

        customer_service_agent = chat_client.as_agent(
            name="customer_service_agent",
            instructions="""You are a friendly Customer Service Agent. Your role is to:
1. Listen to customer issues with empathy
2. Attempt to resolve simple issues (password reset, billing questions, account info)
3. Recognize when a technical expert is needed (bugs, technical errors, API issues)
4. Recognize when a manager is needed (contracts, policies, escalations, executive decisions)
5. Keep responses concise (1-2 sentences)

Be conversational, helpful, and professional.""",
        )

        response = await customer_service_agent.run(topic)
        response_text = response.text or "(no response)"
        
        yield WorkflowEvent(
            type="agent_message",
            data={"content": response_text},
            source_executor_id="customer_service_agent",
        )

        # Check for handoff scenarios
        if should_escalate_further(response_text) or should_escalate_to_manager(response_text):
            logger.info("Handoff: Customer Service → Product Manager")
            yield WorkflowEvent(
                type="agent_message",
                data={"content": "[System] Transferring to Product Manager (escalation detected)..."},
                source_executor_id="system",
            )

            # Phase 3: Product Manager takes over for escalation
            logger.info("Phase 3: Product Manager (escalation)")
            product_manager_agent = chat_client.as_agent(
                name="product_manager_agent",
                instructions="""You are a Product Manager - final decision authority. Your role is to:
1. Review escalated issues requiring policy or executive decisions
2. Make judgments on product changes, workarounds, or exceptions
3. Consider business impact and customer satisfaction
4. Authorize solutions that may go beyond standard support
5. Provide final decisions with clear rationale (1-2 sentences)

Be authoritative but empathetic.""",
            )

            context = f"Initial Request: {topic}\n\nCustomer Service Agent Response: {response_text}"
            response = await product_manager_agent.run(context)
            response_text = response.text or "(no response)"

            yield WorkflowEvent(
                type="agent_message",
                data={"content": response_text},
                source_executor_id="product_manager_agent",
            )

        elif should_escalate_to_technical(response_text):
            logger.info("Handoff: Customer Service → Technical Expert")
            yield WorkflowEvent(
                type="agent_message",
                data={"content": "[System] Transferring to Technical Expert..."},
                source_executor_id="system",
            )

            # Phase 2: Technical Expert takes over
            logger.info("Phase 2: Technical Expert")
            technical_expert_agent = chat_client.as_agent(
                name="technical_expert_agent",
                instructions="""You are a Technical Expert. Your role is to:
1. Analyze technical issues in depth
2. Provide troubleshooting steps and solutions
3. Explain technical concepts clearly
4. Determine if this is a product bug or user error
5. Keep response concise but technical (2-3 sentences)

Be technical but clear.""",
            )

            context = f"Initial Request: {topic}\n\nCustomer Service Agent Response: {response_text}"
            response = await technical_expert_agent.run(context)
            response_text = response.text or "(no response)"

            yield WorkflowEvent(
                type="agent_message",
                data={"content": response_text},
                source_executor_id="technical_expert_agent",
            )

        # Final workflow completion
        logger.info("Handoff workflow completed")
        yield WorkflowEvent(
            type="workflow_complete",
            data={"content": "Handoff workflow completed"},
            source_executor_id="system",
        )

    except Exception as e:
        logger.exception("Handoff workflow error: %s", str(e))
        yield WorkflowEvent(
            type="error",
            data={"content": f"Workflow error: {str(e)[:200]}"},
            source_executor_id="system"
        )



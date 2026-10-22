# Copyright (c) Microsoft. All rights reserved.

"""
Handoff Workflow - Dynamic agent transfer based on context.

This workflow demonstrates handoff orchestration where agents transfer
control to one another based on predefined rules. No central orchestrator—
agents communicate directly in a mesh topology.

Flow:
1. Customer Service Agent analyzes the request
2. If technical issue detected → handoff to Technical Expert
3. If escalation required → handoff to Product Manager
4. Each agent has full context of previous exchanges
5. No human approval checkpoints (control passes automatically)
"""

import logging
from typing import AsyncIterator, Optional

from agent_framework import (
    Agent,
    Message,
    WorkflowEvent,
)
from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential

from . import WorkflowConfig

logger = logging.getLogger(__name__)

# Hardcoded handoff rules
ESCALATION_KEYWORDS = ["escalate", "manager", "senior", "urgent", "critical"]
TECHNICAL_KEYWORDS = ["technical", "bug", "error", "crash", "api", "integration", "code"]
MANAGER_KEYWORDS = ["contract", "billing", "policy", "decision", "executive", "approval"]


def should_escalate_to_technical(message: str) -> bool:
    """Determine if message requires technical expertise."""
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in TECHNICAL_KEYWORDS)


def should_escalate_to_manager(message: str) -> bool:
    """Determine if message requires management decision."""
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in MANAGER_KEYWORDS)


def should_escalate_further(message: str) -> bool:
    """Determine if escalation to higher level is needed."""
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in ESCALATION_KEYWORDS)


async def create_customer_service_agent(config: WorkflowConfig) -> Agent:
    """Create Customer Service Agent - first responder."""
    return Agent(
        name="customer_service_agent",
        model=config.azure_openai_chat_deployment,
        client_factory=lambda: _create_chat_client(config),
        instructions="""You are a friendly Customer Service Agent. Your role is to:
1. Listen to customer issues with empathy
2. Attempt to resolve simple issues (password reset, billing questions, account info)
3. Recognize when a technical expert is needed (bugs, technical errors, API issues)
4. Recognize when a manager is needed (contracts, policies, escalations, executive decisions)
5. When you need to handoff, explicitly say:
   - "I'm connecting you with our Technical Expert." if technical issue
   - "I'm escalating this to our Product Manager." if management decision needed
   - "This needs senior management review." if further escalation

Be conversational, helpful, and professional.""",
    )


async def create_technical_expert_agent(config: WorkflowConfig) -> Agent:
    """Create Technical Expert Agent - handles technical issues."""
    return Agent(
        name="technical_expert_agent",
        model=config.azure_openai_chat_deployment,
        client_factory=lambda: _create_chat_client(config),
        instructions="""You are a Technical Expert. Your role is to:
1. Analyze technical issues in depth
2. Provide troubleshooting steps and solutions
3. Explain technical concepts clearly to non-technical users
4. Determine if this is a product bug or user error
5. Escalate to Product Manager if:
   - It's a critical system issue requiring architecture changes
   - It affects billing or multiple customers
   - It requires executive decision
6. When handing off to Product Manager, say:
   - "This issue requires a management decision. Let me connect you with our Product Manager."

Be technical but clear, provide step-by-step guidance.""",
    )


async def create_product_manager_agent(config: WorkflowConfig) -> Agent:
    """Create Product Manager Agent - final authority."""
    return Agent(
        name="product_manager_agent",
        model=config.azure_openai_chat_deployment,
        client_factory=lambda: _create_chat_client(config),
        instructions="""You are a Product Manager - the final decision authority. Your role is to:
1. Review issues that require policy or executive decisions
2. Make judgments on product changes, workarounds, or exceptions
3. Consider business impact and customer satisfaction
4. Authorize solutions that may go beyond standard support
5. Provide final decisions with clear rationale
6. Ensure customer feels heard and understood

Be authoritative but empathetic, provide business-justified decisions.""",
    )


def _create_chat_client(config: WorkflowConfig) -> OpenAIChatCompletionClient:
    """Create OpenAI chat client with configured credentials."""
    if config.azure_openai_api_key:
        return OpenAIChatCompletionClient(
            model=config.azure_openai_chat_deployment,
            azure_endpoint=config.azure_openai_endpoint,
            api_version=config.azure_openai_api_version,
            api_key=config.azure_openai_api_key,
        )
    else:
        return OpenAIChatCompletionClient(
            model=config.azure_openai_chat_deployment,
            azure_endpoint=config.azure_openai_endpoint,
            api_version=config.azure_openai_api_version,
            credential=AzureCliCredential(),
        )


async def run_handoff_workflow(
    config: WorkflowConfig,
    topic: str = "I need technical support for my service account."
) -> AsyncIterator[WorkflowEvent]:
    """Run the handoff workflow.
    
    Demonstrates handoff orchestration where agents transfer control
    based on predefined rules. Control is explicit and passes based
    on message content.
    
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
            data={"message": config_error},
            source_executor_id="system"
        )
        return
    
    try:
        # Create agents
        logger.info("Creating handoff agents...")
        customer_service = await create_customer_service_agent(config)
        technical_expert = await create_technical_expert_agent(config)
        product_manager = await create_product_manager_agent(config)
        
        # Conversation history shared across all agents
        conversation: list[Message] = []
        
        # Initial message from user
        conversation.append(Message(role="user", content=topic))
        yield WorkflowEvent(
            type="agent_message",
            data={"message": f"Customer: {topic}"},
            source_executor_id="customer",
        )
        
        # Phase 1: Customer Service Agent handles initial request
        logger.info("Phase 1: Customer Service Agent")
        yield WorkflowEvent(
            type="agent_message",
            data={"message": "👤 Customer Service Agent is reviewing your request..."},
            source_executor_id="system",
        )
        
        response = await customer_service.invoke(conversation)
        response_text = response.get("content", "I'll help you with that.")
        conversation.append(Message(role="assistant", content=response_text))
        
        yield WorkflowEvent(
            type="agent_message",
            data={"message": response_text},
            source_executor_id="customer_service_agent",
        )
        
        # Check for handoff: Technical issue?
        if should_escalate_to_technical(response_text) and not should_escalate_further(response_text):
            logger.info("Handoff: Customer Service → Technical Expert")
            yield WorkflowEvent(
                type="agent_message",
                data={"message": "🔄 Transferring to Technical Expert..."},
                source_executor_id="system",
            )
            
            # Phase 2: Technical Expert takes over
            logger.info("Phase 2: Technical Expert")
            response = await technical_expert.invoke(conversation)
            response_text = response.get("content", "I'll diagnose this technical issue.")
            conversation.append(Message(role="assistant", content=response_text))
            
            yield WorkflowEvent(
                type="agent_message",
                data={"message": response_text},
                source_executor_id="technical_expert_agent",
            )
            
            # Check for further escalation
            if should_escalate_further(response_text) or should_escalate_to_manager(response_text):
                logger.info("Handoff: Technical Expert → Product Manager")
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": "🔄 Escalating to Product Manager..."},
                    source_executor_id="system",
                )
                
                # Phase 3: Product Manager makes final decision
                logger.info("Phase 3: Product Manager")
                response = await product_manager.invoke(conversation)
                response_text = response.get("content", "I'll make a management decision on this.")
                conversation.append(Message(role="assistant", content=response_text))
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": response_text},
                    source_executor_id="product_manager_agent",
                )
        
        # Check for direct escalation to manager (non-technical)
        elif should_escalate_to_manager(response_text):
            logger.info("Handoff: Customer Service → Product Manager (non-technical)")
            yield WorkflowEvent(
                type="agent_message",
                data={"message": "🔄 Connecting you with Product Manager..."},
                source_executor_id="system",
            )
            
            # Phase 2b: Product Manager (direct from customer service)
            logger.info("Phase 2b: Product Manager (direct)")
            response = await product_manager.invoke(conversation)
            response_text = response.get("content", "I'll handle this policy matter.")
            conversation.append(Message(role="assistant", content=response_text))
            
            yield WorkflowEvent(
                type="agent_message",
                data={"message": response_text},
                source_executor_id="product_manager_agent",
            )
        
        # Workflow complete
        logger.info("Handoff workflow complete")
        yield WorkflowEvent(
            type="workflow_complete",
            data={
                "summary": "Support request processed through handoff orchestration",
                "agents_involved": list(set([
                    a for msg in conversation 
                    for a in ["customer_service_agent", "technical_expert_agent", "product_manager_agent"]
                ])),
            },
            source_executor_id="system",
        )
        
    except Exception as e:
        logger.error(f"Handoff workflow error: {e}", exc_info=True)
        yield WorkflowEvent(
            type="error",
            data={"message": f"Workflow error: {str(e)}"},
            source_executor_id="system",
        )

# Copyright (c) Microsoft. All rights reserved.

"""
Magentic Workflow - Manager-coordinated specialist collaboration.

This workflow demonstrates magentic orchestration where a dedicated
manager coordinates specialized agents, dynamically selecting which
agent acts next based on task context and progress.

Flow:
1. Manager receives task and creates an action plan
2. Manager selects and delegates to specialists (Researcher, Evaluator, Synthesizer)
3. Manager reviews each specialist's output
4. Manager can request revisions or continue to next phase
5. Manager synthesizes final result
6. Human approval only on final output (manager controls intermediate approvals)
"""

import json
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

# Maximum iterations to prevent infinite loops
MAX_ITERATIONS = 3


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


async def create_magentic_manager(config: WorkflowConfig) -> Agent:
    """Create Magentic Manager - coordinates specialists and makes decisions."""
    return Agent(
        name="magentic_manager",
        model=config.azure_openai_chat_deployment,
        client_factory=lambda: _create_chat_client(config),
        instructions="""You are a Magentic Manager - a highly capable orchestrator and decision-maker.

Your responsibilities:
1. ANALYZE the user's request and create a clear action plan
2. FORMAT your plan as: "PLAN: Step 1: [action]. Step 2: [action]. Step 3: [action]."
3. DELEGATE work to specialists:
   - Say "DELEGATE_RESEARCHER: [specific research task]"
   - Say "DELEGATE_EVALUATOR: [evaluation criteria and specialist output to evaluate]"
   - Say "DELEGATE_SYNTHESIZER: [synthesis instructions with all materials to synthesize]"
4. REVIEW each specialist's output and either:
   - Accept: "ACCEPT_OUTPUT: [specialist name] - this is good"
   - Request revision: "REVISE_OUTPUT: [specialist name] - [specific feedback]"
5. SYNTHESIZE the final result and present it clearly

Be systematic, think step-by-step, and manage quality across all phases.
Make definitive decisions on approvals/rejections—do not defer to humans for intermediate steps.""",
    )


async def create_researcher_agent(config: WorkflowConfig) -> Agent:
    """Create Researcher Agent - gathers and synthesizes information."""
    return Agent(
        name="researcher",
        model=config.azure_openai_chat_deployment,
        client_factory=lambda: _create_chat_client(config),
        instructions="""You are a Research Specialist. Your role is to:
1. Gather comprehensive information on assigned research topics
2. Identify key trends, data points, and patterns
3. Provide well-structured findings with sources/reasoning
4. Be thorough but concise

When given a research task, deliver detailed yet organized findings.""",
    )


async def create_evaluator_agent(config: WorkflowConfig) -> Agent:
    """Create Evaluator Agent - analyzes and evaluates information."""
    return Agent(
        name="evaluator",
        model=config.azure_openai_chat_deployment,
        client_factory=lambda: _create_chat_client(config),
        instructions="""You are an Evaluation and Analysis Specialist. Your role is to:
1. Receive research findings or work from other specialists
2. Analyze quality, accuracy, and completeness
3. Identify strengths and weaknesses
4. Extract key insights and implications
5. Provide critical assessment with structured feedback

When evaluating content, be thorough but fair in your assessment.""",
    )


async def create_synthesizer_agent(config: WorkflowConfig) -> Agent:
    """Create Synthesizer Agent - creates coherent final output."""
    return Agent(
        name="synthesizer",
        model=config.azure_openai_chat_deployment,
        client_factory=lambda: _create_chat_client(config),
        instructions="""You are a Synthesis and Communication Specialist. Your role is to:
1. Take research findings and evaluations
2. Create a coherent, polished final output
3. Structure information logically with clear headings
4. Write in professional, accessible language
5. Ensure all key insights are included and well-explained

When synthesizing, create a compelling narrative that integrates all materials.""",
    )


async def run_magentic_workflow(
    config: WorkflowConfig,
    topic: str = "Analyze market trends and provide recommendations"
) -> AsyncIterator[WorkflowEvent]:
    """Run the magentic workflow.
    
    Demonstrates magentic orchestration where a manager coordinates
    specialists, dynamically routing work and managing quality.
    
    Args:
        config: WorkflowConfig with Azure OpenAI settings
        topic: Task for the manager to coordinate
        
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
        logger.info("Creating magentic agents...")
        manager = await create_magentic_manager(config)
        researcher = await create_researcher_agent(config)
        evaluator = await create_evaluator_agent(config)
        synthesizer = await create_synthesizer_agent(config)
        
        # Shared conversation for manager
        manager_conversation: list[Message] = [
            Message(role="user", content=f"Task: {topic}")
        ]
        
        # Specialist outputs storage
        specialist_outputs = {}
        iteration = 0
        
        # Initial yield
        yield WorkflowEvent(
            type="agent_message",
            data={"message": f"📋 Task: {topic}"},
            source_executor_id="user",
        )
        
        # Manager creates initial plan
        logger.info("Manager creating plan...")
        yield WorkflowEvent(
            type="agent_message",
            data={"message": "🤖 Manager is creating an action plan..."},
            source_executor_id="system",
        )
        
        response = await manager.invoke(manager_conversation)
        plan_text = response.get("content", "Plan created.")
        manager_conversation.append(Message(role="assistant", content=plan_text))
        
        yield WorkflowEvent(
            type="agent_message",
            data={"message": plan_text},
            source_executor_id="magentic_manager",
        )
        
        # Main orchestration loop (with iteration limit)
        while iteration < MAX_ITERATIONS:
            iteration += 1
            logger.info(f"Magentic iteration {iteration}")
            
            # Parse manager's plan for delegations
            if "DELEGATE_RESEARCHER:" in plan_text:
                logger.info("Manager delegating to Researcher...")
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": "🔍 Researcher is gathering information..."},
                    source_executor_id="system",
                )
                
                researcher_task = f"Research task from manager: {topic}"
                researcher_conv = [Message(role="user", content=researcher_task)]
                researcher_response = await researcher.invoke(researcher_conv)
                research_text = researcher_response.get("content", "Research completed.")
                specialist_outputs["researcher"] = research_text
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": research_text},
                    source_executor_id="researcher",
                )
                
                # Manager reviews researcher output
                manager_conversation.append(
                    Message(role="user", content=f"Researcher output:\n{research_text}\nReview this and decide to accept or request revisions.")
                )
                
                response = await manager.invoke(manager_conversation)
                review_text = response.get("content", "Output accepted.")
                manager_conversation.append(Message(role="assistant", content=review_text))
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": review_text},
                    source_executor_id="magentic_manager",
                )
                plan_text = review_text
            
            # Check if manager wants evaluator
            if "DELEGATE_EVALUATOR:" in plan_text and "researcher" in specialist_outputs:
                logger.info("Manager delegating to Evaluator...")
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": "🔬 Evaluator is analyzing findings..."},
                    source_executor_id="system",
                )
                
                evaluator_task = f"Evaluate this research for accuracy and completeness:\n{specialist_outputs['researcher']}"
                evaluator_conv = [Message(role="user", content=evaluator_task)]
                evaluator_response = await evaluator.invoke(evaluator_conv)
                evaluation_text = evaluator_response.get("content", "Evaluation completed.")
                specialist_outputs["evaluator"] = evaluation_text
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": evaluation_text},
                    source_executor_id="evaluator",
                )
                
                # Manager reviews evaluator output
                manager_conversation.append(
                    Message(role="user", content=f"Evaluator analysis:\n{evaluation_text}\nDecide how to proceed.")
                )
                
                response = await manager.invoke(manager_conversation)
                review_text = response.get("content", "Analysis accepted.")
                manager_conversation.append(Message(role="assistant", content=review_text))
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": review_text},
                    source_executor_id="magentic_manager",
                )
                plan_text = review_text
            
            # Check if manager wants synthesizer
            if "DELEGATE_SYNTHESIZER:" in plan_text or iteration >= 2:
                logger.info("Manager delegating to Synthesizer...")
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": "✍️ Synthesizer is creating final output..."},
                    source_executor_id="system",
                )
                
                # Prepare synthesis input with all collected materials
                synthesis_materials = "\n".join([
                    f"Research:\n{specialist_outputs.get('researcher', 'N/A')}",
                    f"\nEvaluation:\n{specialist_outputs.get('evaluator', 'N/A')}",
                ])
                
                synthesizer_task = f"Synthesize this into a comprehensive response about: {topic}\n\nMaterials:\n{synthesis_materials}"
                synthesizer_conv = [Message(role="user", content=synthesizer_task)]
                synthesizer_response = await synthesizer.invoke(synthesizer_conv)
                final_output = synthesizer_response.get("content", "Summary created.")
                specialist_outputs["synthesizer"] = final_output
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": final_output},
                    source_executor_id="synthesizer",
                )
                
                # Manager final review
                manager_conversation.append(
                    Message(role="user", content=f"Final output from Synthesizer:\n{final_output}\nProvide your final assessment.")
                )
                
                response = await manager.invoke(manager_conversation)
                final_assessment = response.get("content", "Final output is complete.")
                manager_conversation.append(Message(role="assistant", content=final_assessment))
                
                yield WorkflowEvent(
                    type="agent_message",
                    data={"message": final_assessment},
                    source_executor_id="magentic_manager",
                )
                
                # Break after synthesis
                break
        
        # Workflow complete
        logger.info("Magentic workflow complete")
        yield WorkflowEvent(
            type="workflow_complete",
            data={
                "summary": "Magentic orchestration complete - specialists coordinated by manager",
                "iterations": iteration,
                "specialists": list(specialist_outputs.keys()),
            },
            source_executor_id="system",
        )
        
    except Exception as e:
        logger.error(f"Magentic workflow error: {e}", exc_info=True)
        yield WorkflowEvent(
            type="error",
            data={"message": f"Workflow error: {str(e)}"},
            source_executor_id="system",
        )

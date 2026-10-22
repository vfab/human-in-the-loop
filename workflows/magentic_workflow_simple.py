# Copyright (c) Microsoft. All rights reserved.

"""
Magentic Workflow - Manager-coordinated specialist collaboration (Simplified Implementation).

This is a simplified proof-of-concept of the magentic orchestration pattern
that works with the current Agent Framework API.

Flow:
1. Manager receives task and creates an action plan
2. Manager selects and delegates to specialists
3. Manager reviews specialist output
4. Manager can iterate or synthesize final result
5. No human approval needed (manager controls intermediate approvals)
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

# Maximum iterations to prevent infinite loops
MAX_ITERATIONS = 3


async def run_magentic_workflow(
    config: WorkflowConfig,
    topic: str = "Analyze market trends and provide recommendations"
) -> AsyncIterator[WorkflowEvent]:
    """Run the magentic workflow - simple version.

    Demonstrates magentic orchestration where a manager coordinates
    specialist agents to complete complex tasks.

    Args:
        config: WorkflowConfig with Azure OpenAI settings
        topic: Task/analysis request for the team

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

        logger.info("Starting magentic workflow with topic: %s", topic[:100])

        # Initial task message
        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"Task: {topic}"},
            source_executor_id="user",
        )

        # Phase 1: Manager creates plan
        logger.info("Phase 1: Manager creating plan")
        yield WorkflowEvent(
            type="agent_message",
            data={"content": "[Manager] Analyzing task and creating plan..."},
            source_executor_id="system",
        )

        manager_agent = chat_client.as_agent(
            name="magentic_manager",
            instructions="""You are a Magentic Manager - a coordinator for a specialist team.

Your role:
1. Receive a task/request
2. Create a 3-step plan: PLAN: Step 1: [action]. Step 2: [action]. Step 3: [action].
3. Delegate research to "Researcher Agent" for investigation
4. Delegate analysis to "Evaluator Agent" for assessment
5. Delegate synthesis to "Synthesizer Agent" for final output
6. Review each specialist's work and request revisions if needed
7. Make definitive decisions - no deferral to humans for intermediate steps

Be systematic, plan-driven, and manage quality. Keep responses to 3-4 sentences.""",
        )

        plan_response = await manager_agent.run(f"Task: {topic}")
        plan_text = plan_response.text or "(no plan generated)"

        yield WorkflowEvent(
            type="agent_message",
            data={"content": plan_text},
            source_executor_id="magentic_manager",
        )

        # Phase 2: Researcher gathers information
        logger.info("Phase 2: Researcher gathering information")
        yield WorkflowEvent(
            type="agent_message",
            data={"content": "[Manager] Delegating research..."},
            source_executor_id="system",
        )

        researcher_agent = chat_client.as_agent(
            name="researcher",
            instructions="""You are a Research Specialist on the team.

Your role:
1. Receive research tasks from the Manager
2. Gather comprehensive information on the assigned topic
3. Identify key trends, data points, and patterns
4. Provide well-structured findings (3-4 sentences)

Be thorough and organized.""",
        )

        research_context = f"Task: {topic}\n\nManager's Plan: {plan_text}\n\nResearch this task thoroughly."
        research_response = await researcher_agent.run(research_context)
        research_text = research_response.text or "(no research)"

        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"[Researcher] {research_text}"},
            source_executor_id="researcher",
        )

        # Phase 3: Evaluator analyzes findings
        logger.info("Phase 3: Evaluator analyzing findings")
        yield WorkflowEvent(
            type="agent_message",
            data={"content": "[Manager] Delegating evaluation..."},
            source_executor_id="system",
        )

        evaluator_agent = chat_client.as_agent(
            name="evaluator",
            instructions="""You are an Evaluation Specialist on the team.

Your role:
1. Receive research findings from other specialists
2. Analyze quality, accuracy, and completeness
3. Extract key insights and implications
4. Provide critical assessment (3-4 sentences)

Be thorough and fair in your assessment.""",
        )

        eval_context = f"Task: {topic}\n\nResearch Findings:\n{research_text}\n\nEvaluate the quality and completeness of this research."
        eval_response = await evaluator_agent.run(eval_context)
        eval_text = eval_response.text or "(no evaluation)"

        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"[Evaluator] {eval_text}"},
            source_executor_id="evaluator",
        )

        # Phase 4: Synthesizer creates final output
        logger.info("Phase 4: Synthesizer creating final output")
        yield WorkflowEvent(
            type="agent_message",
            data={"content": "[Manager] Delegating synthesis..."},
            source_executor_id="system",
        )

        synthesizer_agent = chat_client.as_agent(
            name="synthesizer",
            instructions="""You are a Synthesis Specialist on the team.

Your role:
1. Take research findings and evaluations
2. Create a coherent, polished final output
3. Structure information logically
4. Write in professional, accessible language
5. Keep response to 3-4 sentences - create a compelling summary

Integrate all materials into a coherent narrative.""",
        )

        synth_context = f"Task: {topic}\n\nResearch:\n{research_text}\n\nEvaluation:\n{eval_text}\n\nCreate a final synthesis."
        synth_response = await synthesizer_agent.run(synth_context)
        synth_text = synth_response.text or "(no synthesis)"

        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"[Synthesizer] {synth_text}"},
            source_executor_id="synthesizer",
        )

        # Phase 5: Manager approves and completes
        logger.info("Phase 5: Manager final review")
        yield WorkflowEvent(
            type="agent_message",
            data={"content": "[Manager] Reviewing final output..."},
            source_executor_id="system",
        )

        # Manager's final review
        final_review_context = f"Task: {topic}\n\nFinal Output:\n{synth_text}\n\nApprove this output or request revisions (keep to 1-2 sentences)."
        final_response = await manager_agent.run(final_review_context)
        final_text = final_response.text or "(no final review)"

        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"[Manager Final Review] {final_text}"},
            source_executor_id="magentic_manager",
        )

        # Workflow completion
        logger.info("Magentic workflow completed")
        yield WorkflowEvent(
            type="workflow_complete",
            data={"content": "Magentic workflow completed"},
            source_executor_id="system",
        )

    except Exception as e:
        logger.exception("Magentic workflow error: %s", str(e))
        yield WorkflowEvent(
            type="error",
            data={"content": f"Workflow error: {str(e)[:200]}"},
            source_executor_id="system"
        )




# Copyright (c) Microsoft. All rights reserved.

"""
Concurrent Request Workflow - Multi-perspective analysis with human approval.

Extracted from: concurrent_request_info.py

This workflow demonstrates concurrent orchestration where multiple agents
(technical analyst, business analyst, UX analyst) analyze a topic in parallel,
with human-in-the-loop approval of each analyst's output and of the final synthesized summary.
Everything happens in the dashboard; no email is sent.

Flow:
1. Three agents analyze a topic concurrently from different perspectives
2. The human reviews all three responses in one popup, approving or rejecting each
3. A custom aggregator synthesizes their outputs using an LLM
4. The human accepts or rejects the synthesized summary
"""

import logging
from dataclasses import dataclass
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

from . import WorkflowConfig, reply_approved

logger = logging.getLogger(__name__)

# Display names shown in the dashboard for each analyst
AGENT_LABELS = {
    "technical_analyst": "Technical Analyst",
    "business_analyst": "Business Analyst",
    "ux_analyst": "UX Analyst",
}


@dataclass
class ConcurrentWorkflowState:
    """Track state during workflow execution."""
    chat_client: Optional[OpenAIChatCompletionClient] = None
    summary_accepted: bool = False
    workflow_complete: bool = False
    pending_responses: Optional[dict[str, AgentRequestInfoResponse]] = None


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
    human-in-the-loop approval of each analyst's output and of the final summary.
    No email is sent; all prompts appear in the dashboard.
    
    Args:
        config: WorkflowConfig with Azure OpenAI settings
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
            .with_request_info(agents=["technical_analyst", "business_analyst", "ux_analyst"])
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
            pending_requests: list[WorkflowEvent] = []
            
            # Process events
            async for event in stream:
                if isinstance(event, WorkflowEvent) and event.type == "request_info":
                    # Collect every analyst's output so the human reviews them together
                    if isinstance(event.data, AgentExecutorResponse):
                        pending_requests.append(event)
                
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
                        
                        # Ask the human, in the app, whether to accept the summary
                        reply = yield WorkflowEvent(
                            type="approval_required",
                            data={
                                "request_id": "summary_review",
                                "prompt": "Accept this synthesized summary?",
                                "content": summary_text
                            },
                            source_executor_id="system"
                        )
                        
                        state.summary_accepted = reply_approved(reply)
                        yield WorkflowEvent(
                            type="agent_message",
                            data={"content": (
                                "✓ Summary accepted" if state.summary_accepted
                                else "✗ Summary rejected"
                            )},
                            source_executor_id="system"
                        )
                    
                    state.workflow_complete = True
                
                elif isinstance(event, WorkflowEvent) and event.type == "status":
                    if event.state == WorkflowRunState.IDLE:
                        state.workflow_complete = True
            
            if pending_requests:
                # One review step for all analysts: the human approves or rejects each response
                for request in pending_requests:
                    yield WorkflowEvent(
                        type="agent_message",
                        data={
                            "agent": request.source_executor_id,
                            "content": request.data.agent_response.text
                        },
                        source_executor_id=request.source_executor_id
                    )
                
                reply = yield WorkflowEvent(
                    type="approval_batch",
                    data={
                        "request_id": "analyst_review",
                        "prompt": "Review each analyst's response",
                        "items": [
                            {
                                "request_id": request.request_id,
                                "agent": request.source_executor_id,
                                "label": AGENT_LABELS.get(
                                    request.source_executor_id, request.source_executor_id
                                ),
                                "content": request.data.agent_response.text,
                            }
                            for request in pending_requests
                        ],
                    },
                    source_executor_id="system"
                )
                
                # Analysts the human did not decide on (e.g. timeout) are accepted as-is
                decisions = (reply or {}).get("decisions") or {}
                responses: dict[str, AgentRequestInfoResponse] = {}
                for request in pending_requests:
                    if decisions.get(request.request_id, True):
                        responses[request.request_id] = AgentRequestInfoResponse.approve()
                    else:
                        yield WorkflowEvent(
                            type="agent_message",
                            data={"content": f"{AGENT_LABELS.get(request.source_executor_id, request.source_executor_id)} rejected; asking for a revision."},
                            source_executor_id="system"
                        )
                        responses[request.request_id] = AgentRequestInfoResponse.from_strings([
                            "The reviewer rejected this analysis. Please reconsider and "
                            "provide a revised, more balanced perspective."
                        ])
                state.pending_responses = responses
                
                rejected = [r for r in pending_requests if not decisions.get(r.request_id, True)]
                yield WorkflowEvent(
                    type="progress",
                    data={"message": (
                        "Asking the analysts to revise…" if rejected
                        else "Synthesizing the analysts' responses…"
                    )},
                    source_executor_id="system"
                )
        
        # Send completion event
        if summary_text:
            yield WorkflowEvent(
                type="workflow_complete",
                data={
                    "status": "completed",
                    "summary": summary_text,
                    "summary_accepted": state.summary_accepted
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

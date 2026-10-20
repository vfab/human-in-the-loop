# Copyright (c) Microsoft. All rights reserved.

"""
Sequential Workflow - Document review with human steering.

Extracted from: sequential_request_info.py

This workflow demonstrates a sequential pipeline where multiple agents
(drafter, editor, finalizer) work on a document in sequence, with
human-in-the-loop steering before the editor's review.

Flow:
1. Drafter creates initial document draft
2. Editor reviews and suggests improvements (with human steering)
3. Finalizer polishes and creates final version
4. Human approval before completing
"""

import logging
from typing import AsyncIterator, Optional

from agent_framework import (
    Message,
    WorkflowEvent,
    WorkflowRunState,
)
from agent_framework._workflows._agent_executor import AgentExecutorResponse
from agent_framework_orchestrations import AgentRequestInfoResponse, SequentialBuilder
from agent_framework_openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential

from . import WorkflowConfig

logger = logging.getLogger(__name__)


async def run_sequential_workflow(
    config: WorkflowConfig,
    topic: str = "Write a brief introduction to artificial intelligence."
) -> AsyncIterator[WorkflowEvent]:
    """Run the sequential request workflow.
    
    Demonstrates sequential orchestration with human steering before
    the editor's review of a document.
    
    Args:
        config: WorkflowConfig with Azure OpenAI settings
        topic: Topic for the document
        
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
        
        logger.info("Starting sequential workflow")
        
        # Create agents for sequential document review
        drafter = chat_client.as_agent(
            name="drafter",
            instructions="You are a document drafter. When given a topic, create a brief draft (2-3 sentences).",
        )
        
        editor = chat_client.as_agent(
            name="editor",
            instructions=(
                "You are an editor. Review the draft and suggest improvements. "
                "Incorporate any human feedback that was provided."
            ),
        )
        
        finalizer = chat_client.as_agent(
            name="finalizer",
            instructions=(
                "You are a finalizer. Take the edited content and create a polished final version. "
                "Incorporate any additional feedback provided."
            ),
        )
        
        # Build workflow with request info for editor only
        workflow = (
            SequentialBuilder(participants=[drafter, editor, finalizer])
            .with_request_info(agents=["editor"])
            .build()
        )
        
        yield WorkflowEvent(
            type="agent_message",
            data={"content": f"Starting document review: {topic}"},
            source_executor_id="system"
        )
        
        # Run workflow with human-in-the-loop
        pending_responses: Optional[dict[str, AgentRequestInfoResponse]] = None
        workflow_complete = False
        
        while not workflow_complete:
            # Run or continue workflow
            stream = (
                workflow.run(responses=pending_responses, stream=True)
                if pending_responses
                else workflow.run(topic, stream=True)
            )
            
            pending_responses = None
            
            # Process events
            async for event in stream:
                if isinstance(event, WorkflowEvent) and event.type == "request_info":
                    if isinstance(event.data, AgentExecutorResponse):
                        # Display editor's response for human steering
                        agent_response = event.data.agent_response.text
                        yield WorkflowEvent(
                            type="agent_message",
                            data={
                                "agent": event.source_executor_id,
                                "content": agent_response
                            },
                            source_executor_id=event.source_executor_id
                        )
                        
                        # Request human input to steer the editor
                        yield WorkflowEvent(
                            type="input_required",
                            data={
                                "request_id": event.request_id,
                                "prompt": "Provide feedback to steer the editor (or press enter to skip):",
                                "agent": "editor"
                            },
                            source_executor_id="system"
                        )
                        
                        # Default: approve without steering
                        pending_responses = {
                            event.request_id: AgentRequestInfoResponse.approve()
                        }
                
                elif isinstance(event, WorkflowEvent) and event.type == "output":
                    logger.info("Workflow complete")
                    if event.data:
                        yield WorkflowEvent(
                            type="agent_message",
                            data={"content": f"Final Document:\n{event.data}"},
                            source_executor_id="system"
                        )
                    workflow_complete = True
                
                elif isinstance(event, WorkflowEvent) and event.type == "status":
                    if event.state == WorkflowRunState.IDLE:
                        workflow_complete = True
        
        yield WorkflowEvent(
            type="workflow_complete",
            data={"status": "completed"},
            source_executor_id="system"
        )
    
    except Exception as e:
        logger.exception("Error in sequential workflow: %s", e)
        yield WorkflowEvent(
            type="error",
            data={"message": str(e)},
            source_executor_id="system"
        )

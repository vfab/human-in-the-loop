# Copyright (c) Microsoft. All rights reserved.

"""
HITL Demo Dashboard - Main FastAPI Server

This is the main entry point for the Human-In-The-Loop demonstration dashboard.
It serves a web interface that discovers and runs multiple HITL workflow samples
as tabs in a single dashboard, with real-time event streaming via WebSocket.

Architecture:
- FastAPI backend serves REST API + WebSocket server
- HTML/CSS/JS frontend provides tabbed UI with sidebar navigation
- Each workflow runs asynchronously and streams events to connected clients
- Shared WorkflowConfig provides Azure OpenAI and SMTP credentials
- Approval/input events are captured and returned from the UI via modal dialogs

Endpoints:
- GET  /                            - Serve dashboard HTML
- GET  /workflows                   - List available workflows
- POST /api/workflows/{id}/start    - Start a workflow with optional input
- WS   /ws/workflow/{id}/{run_id}   - WebSocket stream for workflow events
- POST /api/workflows/{id}/approve  - Handle approval response
- POST /api/workflows/{id}/input    - Handle text input response

Environment Variables (from .env):
- AZURE_OPENAI_API_KEY
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_CHAT_DEPLOYMENT_NAME (or AZURE_OPENAI_CHAT_MODEL)
- AZURE_OPENAI_API_VERSION (default: 2024-10-21)
- SMTP_HOST (optional, for email workflows)
- SMTP_PORT (default: 587)
- SMTP_USER (optional)
- SMTP_PASSWORD (or GMAIL_SMTP_APP_PASSWORD)
- EMAIL_RECIPIENT (default email target)
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Import workflow modules (Phase 1 extraction)
from workflows import WorkflowConfig
from workflows.concurrent_workflow import run_concurrent_workflow
from workflows.group_chat_workflow import run_group_chat_workflow
from workflows.sequential_workflow import run_sequential_workflow
from workflows.approval_workflow import run_approval_workflow
from workflows.game_workflow import run_game_workflow
from workflows.handoff_workflow import run_handoff_workflow
from workflows.magentic_workflow import run_magentic_workflow

load_dotenv()
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration & Data Models
# ============================================================================


class WorkflowMetadata(BaseModel):
    """Metadata for a workflow."""
    id: str
    name: str
    description: str
    input_required: bool = False
    input_placeholder: str = ""


class WorkflowEventMessage(BaseModel):
    """Message sent over WebSocket to client."""
    type: str  # "agent_message", "approval_required", "input_required", "workflow_complete", "error"
    timestamp: str  # ISO format
    agent_name: str = ""
    content: str = ""
    request_id: str = ""  # For approval/input responses
    severity: str = "info"  # "info", "warning", "error"
    data: dict[str, Any] = {}  # Extra context


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="HITL Demo Dashboard",
    description="Human-In-The-Loop demonstration workflows",
    version="1.0.0"
)

# Configuration loaded once at startup
_config: WorkflowConfig | None = None
_workflow_runners: dict[str, Any] = {}  # Placeholder for workflow runner functions
_active_runs: dict[str, dict[str, Any]] = {}  # Track running workflows
_TOPIC_REQUIRED = {"concurrent", "group_chat", "sequential", "handoff", "magentic"}  # Workflows that need a user topic


@app.on_event("startup")
async def startup():
    """Initialize configuration and workflow registry."""
    global _config
    _config = WorkflowConfig.from_env()
    
    # Validate Azure OpenAI config
    if not _config.azure_openai_api_key or not _config.azure_openai_endpoint:
        logger.warning(
            "Missing Azure OpenAI configuration. "
            "Please set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT in .env"
        )
    
    # Register workflow runners
    _workflow_runners["concurrent"] = run_concurrent_workflow
    _workflow_runners["group_chat"] = run_group_chat_workflow
    _workflow_runners["sequential"] = run_sequential_workflow
    _workflow_runners["approval"] = run_approval_workflow
    _workflow_runners["game"] = run_game_workflow
    _workflow_runners["handoff"] = run_handoff_workflow
    _workflow_runners["magentic"] = run_magentic_workflow
    
    logger.info("HITL Dashboard starting on http://localhost:8000")
    logger.info("Available workflows: %s", list(_workflow_runners.keys()))


# ============================================================================
# Static Files & UI Routes
# ============================================================================

@app.get("/")
async def serve_dashboard() -> FileResponse:
    """Serve the main dashboard HTML page."""
    index_path = Path(__file__).parent / "static" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard HTML not found")
    return FileResponse(index_path)


# Mount static files (CSS, JS, images)
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# ============================================================================
# REST API Routes
# ============================================================================

@app.get("/workflows")
async def list_workflows() -> list[WorkflowMetadata]:
    """List all available workflows."""
    workflows = [
        WorkflowMetadata(
            id="sequential",
            name="Sequential",
            description="Sequential workflow with human steering",
            input_required=True,
            input_placeholder="Enter content to review..."
        ),
        WorkflowMetadata(
            id="concurrent",
            name="Concurrent",
            description="Multi-perspective analysis with concurrent agents and approval",
            input_required=True,
            input_placeholder="Enter topic to analyze..."
        ),
        WorkflowMetadata(
            id="handoff",
            name="Handoff",
            description="Agent Framework pattern: Customer support with automatic handoff between agents",
            input_required=True,
            input_placeholder="Describe your support issue..."
        ),
        WorkflowMetadata(
            id="group_chat",
            name="Group Chat",
            description="Sequential group chat with steering input",
            input_required=True,
            input_placeholder="Enter discussion topic..."
        ),
        WorkflowMetadata(
            id="magentic",
            name="Magentic",
            description="Agent Framework pattern: Manager-coordinated multi-agent analysis",
            input_required=True,
            input_placeholder="Enter task for analysis..."
        ),
        WorkflowMetadata(
            id="game",
            name="Guessing Game",
            description="Interactive number guessing game with agent",
            input_required=False,
            input_placeholder=""
        ),
    ]
    return workflows


@app.post("/api/workflows/{workflow_id}/start")
async def start_workflow(workflow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Start a workflow execution.
    
    Args:
        workflow_id: ID of the workflow to run
        body: {"input": "optional input string"}
    
    Returns:
        {"run_id": "unique run identifier", "status": "started"}
    """
    if workflow_id not in _workflow_runners:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    
    run_id = str(uuid.uuid4())
    input_text = body.get("input", "")
    
    if workflow_id in _TOPIC_REQUIRED and not str(input_text).strip():
        raise HTTPException(status_code=400, detail="A topic is required for this workflow")
    
    _active_runs[run_id] = {
        "workflow_id": workflow_id,
        "input": input_text,
        "started_at": datetime.utcnow().isoformat(),
        "status": "running",
        "pending_responses": {},  # Responses that arrived with no waiter registered
        "waiters": {},  # request_id -> Future resolved by the approve/input endpoints
    }
    
    logger.info("Started workflow %s with run_id %s", workflow_id, run_id)
    return {"run_id": run_id, "status": "started"}


@app.post("/api/workflows/{workflow_id}/approve")
async def submit_approval(workflow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Submit approval response for a pending approval request.
    
    Args:
        workflow_id: ID of the workflow
        body: {
            "run_id": "run identifier",
            "request_id": "request identifier",
            "approved": true/false,
            "feedback": "optional feedback"
        }
    
    Returns:
        {"status": "accepted"}
    """
    run_id = body.get("run_id")
    request_id = body.get("request_id")
    approved = body.get("approved", False)
    feedback = body.get("feedback", "")
    decisions = body.get("decisions") or {}
    
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    
    _deliver_response(run_id, request_id, {
        "type": "approval",
        "approved": approved,
        "feedback": feedback,
        "decisions": decisions,
    })
    
    logger.info("Approval submitted for run %s request %s: %s", run_id, request_id, approved)
    return {"status": "accepted"}


@app.post("/api/workflows/{workflow_id}/input")
async def submit_input(workflow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Submit text input response for a pending input request.
    
    Args:
        workflow_id: ID of the workflow
        body: {
            "run_id": "run identifier",
            "request_id": "request identifier",
            "input": "user input text"
        }
    
    Returns:
        {"status": "accepted"}
    """
    run_id = body.get("run_id")
    request_id = body.get("request_id")
    input_text = body.get("input", "")
    
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    
    _deliver_response(run_id, request_id, {
        "type": "input",
        "input": input_text,
    })
    
    logger.info("Input submitted for run %s request %s", run_id, request_id)
    return {"status": "accepted"}


# ============================================================================
# Helper Functions
# ============================================================================

def _deliver_response(run_id: str, request_id: str, response: dict[str, Any]) -> None:
    """Hand a human's response to the workflow that is waiting on it."""
    run_info = _active_runs[run_id]
    waiter = run_info["waiters"].get(request_id)
    if waiter is not None and not waiter.done():
        waiter.set_result(response)
    else:
        run_info["pending_responses"][request_id] = response


async def _watch_disconnect(websocket: WebSocket) -> None:
    """Return when the client goes away (the dashboard sends no messages of its own)."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


async def _request_response(
    websocket: WebSocket,
    run_id: str,
    request_id: str,
    payload: dict[str, Any],
    timeout_seconds: int = 300,
) -> dict[str, Any] | None:
    """Send an approval/input request to the client and wait for the human's reply.

    The waiter is registered before the request is sent so a fast reply cannot be lost.
    Returns None on timeout; raises WebSocketDisconnect if the client leaves while waiting.
    """
    run_info = _active_runs[run_id]
    waiter: asyncio.Future = asyncio.get_running_loop().create_future()
    run_info["waiters"][request_id] = waiter
    disconnect_task = asyncio.ensure_future(_watch_disconnect(websocket))
    try:
        await websocket.send_json(payload)
        done, _ = await asyncio.wait(
            {waiter, disconnect_task},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if waiter in done:
            return waiter.result()
        if disconnect_task in done:
            raise WebSocketDisconnect()
        logger.warning("Timed out waiting for response to %s", request_id)
        return None
    finally:
        run_info["waiters"].pop(request_id, None)
        disconnect_task.cancel()


# ============================================================================
# WebSocket Routes
# ============================================================================

@app.websocket("/ws/workflow/{workflow_id}/{run_id}")
async def websocket_workflow_stream(websocket: WebSocket, workflow_id: str, run_id: str):
    """WebSocket endpoint for streaming workflow events to the client.
    
    The workflow runs in the background and streams events (agent messages,
    approval requests, input requests, completion) to all connected clients.
    
    Flow:
    1. Client connects via WebSocket
    2. Backend starts workflow execution (if not already started)
    3. Backend yields events from the workflow
    4. Backend sends each event to the client as JSON
    5. Client handles events (display, show modals, etc.)
    6. Client sends responses back via REST API
    7. Backend injects responses into workflow
    8. Workflow completes and sends "workflow_complete" event
    9. WebSocket closes
    """
    await websocket.accept()
    logger.info("WebSocket connected for workflow %s run %s", workflow_id, run_id)
    
    try:
        if run_id not in _active_runs:
            await websocket.send_json({
                "type": "error",
                "content": "Run not found",
                "severity": "error",
            })
            await websocket.close()
            return
        
        run_info = _active_runs[run_id]
        
        # Send initial status
        await websocket.send_json({
            "type": "workflow_start",
            "timestamp": datetime.utcnow().isoformat(),
            "content": f"Starting {workflow_id} workflow...",
            "severity": "info",
        })
        
        # Execute the workflow
        if workflow_id not in _workflow_runners:
            await websocket.send_json({
                "type": "error",
                "content": f"Unknown workflow: {workflow_id}",
                "severity": "error",
            })
            await websocket.close()
            return
        
        workflow_runner = _workflow_runners[workflow_id]
        user_input = run_info.get("input", "")
        
        logger.info("Starting workflow execution for %s with input: %s", workflow_id, user_input[:100] if user_input else "(none)")
        
        # Stream events from the workflow
        agen = None
        try:
            # Call workflow with appropriate parameters based on workflow type
            if workflow_id == "approval" or workflow_id == "game":
                # Optional scenario (approval) / number range (game) chosen from the sample drop-down
                workflow_stream = workflow_runner(_config, user_input)
            elif workflow_id == "concurrent":
                # Takes analysis_topic parameter
                topic = user_input or "Analyze the impact of large language models on software development."
                workflow_stream = workflow_runner(_config, topic)
            elif workflow_id == "group_chat":
                # Takes topic parameter
                topic = user_input or "Discuss how our team should approach adopting AI tools for productivity."
                workflow_stream = workflow_runner(_config, topic)
            elif workflow_id == "sequential":
                # Takes topic parameter
                topic = user_input or "Write a brief introduction to artificial intelligence."
                workflow_stream = workflow_runner(_config, topic)
            else:
                await websocket.send_json({
                    "type": "error",
                    "content": f"Unknown workflow: {workflow_id}",
                    "severity": "error",
                })
                await websocket.close()
                return
            
            agen = workflow_stream.__aiter__()
            reply: dict[str, Any] | None = None
            
            while True:
                # The reply to the previous approval/input request is sent into the generator
                try:
                    event = await agen.asend(reply)
                except StopAsyncIteration:
                    break
                reply = None
                
                # Handle different event types
                if hasattr(event, 'type'):
                    event_type = event.type
                    event_data = event.data if hasattr(event, 'data') else {}
                    # source_executor_id raises (not AttributeError) for non request_info events,
                    # so read the underlying field the workflows set.
                    event_source = (
                        getattr(event, "_source_executor_id", None)
                        or getattr(event, "executor_id", None)
                        or "system"
                    )
                else:
                    # Handle raw dict events
                    event_type = event.get("type", "unknown")
                    event_data = event.get("data", {})
                    event_source = event.get("source_executor_id", "system")
                
                logger.debug("Workflow event: type=%s, source=%s", event_type, event_source)
                
                # Send agent messages
                if event_type == "agent_message":
                    content = event_data.get("content", "") if isinstance(event_data, dict) else str(event_data)
                    if not str(content).strip():
                        continue
                    agent_name = event_data.get("agent", event_source) if isinstance(event_data, dict) else event_source
                    
                    await websocket.send_json({
                        "type": "agent_message",
                        "timestamp": datetime.utcnow().isoformat(),
                        "agent_name": agent_name,
                        "content": content,
                        "severity": "info",
                    })
                
                # Send approval requests and wait for the human's decision
                elif event_type == "approval_required":
                    data = event_data if isinstance(event_data, dict) else {}
                    request_id = data.get("request_id", str(uuid.uuid4()))
                    
                    reply = await _request_response(websocket, run_id, request_id, {
                        "type": "approval_required",
                        "timestamp": datetime.utcnow().isoformat(),
                        "request_id": request_id,
                        "prompt": data.get("prompt", "Approve?"),
                        "content": data.get("content", ""),
                        "agent_name": data.get("agent", ""),
                        "severity": "info",
                    })
                    if reply is None:
                        reply = {"type": "approval", "approved": False, "feedback": "timed out"}
                        await websocket.send_json({
                            "type": "agent_message",
                            "timestamp": datetime.utcnow().isoformat(),
                            "agent_name": "system",
                            "content": "No response received within 5 minutes; treated as rejected.",
                            "severity": "warning",
                        })
                
                # Send a batch of items to approve individually (one modal, one decision each)
                elif event_type == "approval_batch":
                    data = event_data if isinstance(event_data, dict) else {}
                    request_id = data.get("request_id", str(uuid.uuid4()))
                    
                    reply = await _request_response(websocket, run_id, request_id, {
                        "type": "approval_batch",
                        "timestamp": datetime.utcnow().isoformat(),
                        "request_id": request_id,
                        "prompt": data.get("prompt", "Review each item"),
                        "items": data.get("items", []),
                        "severity": "info",
                    })
                    if reply is None:
                        await websocket.send_json({
                            "type": "agent_message",
                            "timestamp": datetime.utcnow().isoformat(),
                            "agent_name": "system",
                            "content": "No response received within 5 minutes; accepted all responses as-is.",
                            "severity": "warning",
                        })
                
                # Send input requests and wait for the human's text
                elif event_type == "input_required":
                    data = event_data if isinstance(event_data, dict) else {}
                    request_id = data.get("request_id", str(uuid.uuid4()))
                    
                    reply = await _request_response(websocket, run_id, request_id, {
                        "type": "input_required",
                        "timestamp": datetime.utcnow().isoformat(),
                        "request_id": request_id,
                        "prompt": data.get("prompt", "Enter input:"),
                        "options": data.get("options", []),
                        "agent_name": data.get("agent", ""),
                        "severity": "info",
                    })
                    if reply is None:
                        reply = {"type": "input", "input": ""}
                        await websocket.send_json({
                            "type": "agent_message",
                            "timestamp": datetime.utcnow().isoformat(),
                            "agent_name": "system",
                            "content": "No response received within 5 minutes; continuing without input.",
                            "severity": "warning",
                        })
                
                # Progress notes shown while the workflow works between human steps
                elif event_type == "progress":
                    data = event_data if isinstance(event_data, dict) else {}
                    await websocket.send_json({
                        "type": "progress",
                        "timestamp": datetime.utcnow().isoformat(),
                        "content": data.get("message", "Working..."),
                        "severity": "info",
                    })
                
                # Send workflow complete
                elif event_type == "workflow_complete":
                    await websocket.send_json({
                        "type": "workflow_complete",
                        "timestamp": datetime.utcnow().isoformat(),
                        "content": "Workflow completed successfully",
                        "severity": "info",
                    })
                    run_info["status"] = "completed"
                    break
                
                # Send errors
                elif event_type == "error":
                    content = event_data.get("message", str(event_data)) if isinstance(event_data, dict) else str(event_data)
                    await websocket.send_json({
                        "type": "error",
                        "timestamp": datetime.utcnow().isoformat(),
                        "content": content,
                        "severity": "error",
                    })
                
                # Allow other events to pass through (status, etc.)
                else:
                    logger.debug("Unhandled event type: %s", event_type)
        
        except WebSocketDisconnect:
            raise
        
        except asyncio.CancelledError:
            logger.info("Workflow execution cancelled for %s", workflow_id)
            await websocket.send_json({
                "type": "error",
                "content": "Workflow execution cancelled",
                "severity": "warning",
            })
            run_info["status"] = "cancelled"
        
        except Exception as e:
            logger.exception("Error during workflow execution: %s", e)
            await websocket.send_json({
                "type": "error",
                "content": f"Workflow error: {str(e)}",
                "severity": "error",
            })
            run_info["status"] = "error"
        
        finally:
            if agen is not None:
                await agen.aclose()
        
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for workflow %s run %s", workflow_id, run_id)
    except Exception as e:
        logger.exception("Error in WebSocket handler: %s", e)
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"Error: {str(e)}",
                "severity": "error",
            })
        except Exception:
            pass


# ============================================================================
# Health & Debug Routes
# ============================================================================

@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "config_valid": _config is not None and bool(_config.azure_openai_endpoint),
    }


@app.get("/debug/config")
async def debug_config() -> dict[str, Any]:
    """Debug endpoint to check configuration (DO NOT USE IN PRODUCTION)."""
    if not _config:
        return {"error": "Config not initialized"}
    
    return {
        "azure_openai_endpoint": _config.azure_openai_endpoint,
        "azure_openai_chat_deployment": _config.azure_openai_chat_deployment,
        "smtp_host": _config.smtp_host,
        "smtp_user": _config.smtp_user,
        "email_recipient": _config.email_recipient,
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    )
    
    # Start server
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )

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
- AZURE_OPENAI_API_KEY (optional; otherwise uses AzureCliCredential)
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
import smtplib
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from dotenv import load_dotenv

# Import workflow modules (Phase 1 extraction)
from workflows import WorkflowConfig
from workflows.concurrent_workflow import run_concurrent_workflow
from workflows.group_chat_workflow import run_group_chat_workflow
from workflows.sequential_workflow import run_sequential_workflow
from workflows.approval_workflow import (
    run_approval_workflow,
    send_notification_email,
    validate_smtp_config,
)
from workflows.game_workflow import run_game_workflow
from workflows.handoff_workflow_simple import run_handoff_workflow
from workflows.magentic_workflow_simple import run_magentic_workflow

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
    email_notifications_supported: bool = False


class WorkflowEventMessage(BaseModel):
    """Message sent over WebSocket to client."""
    type: str  # "agent_message", "approval_required", "input_required", "workflow_complete", "error"
    timestamp: str  # ISO format
    agent_name: str = ""
    content: str = ""
    request_id: str = ""  # For approval/input responses
    severity: str = "info"  # "info", "warning", "error"
    data: dict[str, Any] = {}  # Extra context


class APIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartWorkflowRequest(APIRequest):
    input: StrictStr = Field(default="", max_length=10_000)
    email_notifications: StrictBool = False


class ApprovalRequest(APIRequest):
    run_id: StrictStr = Field(min_length=1, max_length=64)
    request_id: StrictStr = Field(min_length=1, max_length=128)
    approved: StrictBool = False
    feedback: StrictStr = Field(default="", max_length=4_000)
    decisions: dict[StrictStr, StrictBool] = Field(default_factory=dict, max_length=100)


class InputRequest(APIRequest):
    run_id: StrictStr = Field(min_length=1, max_length=64)
    request_id: StrictStr = Field(min_length=1, max_length=128)
    input: StrictStr = Field(default="", max_length=10_000)


# ============================================================================
# Global State
# ============================================================================

# Configuration loaded once at startup
_config: WorkflowConfig | None = None
_workflow_runners: dict[str, Any] = {}  # Placeholder for workflow runner functions
_active_runs: dict[str, dict[str, Any]] = {}  # Track running workflows
_TOPIC_REQUIRED = {"concurrent", "group_chat", "sequential", "handoff", "magentic"}  # Workflows that need a user topic
_EMAIL_NOTIFICATION_WORKFLOWS = frozenset({"sequential", "concurrent", "group_chat", "approval"})
_STALE_RUN_MAX_AGE_DAYS = int(os.getenv("STALE_RUN_MAX_AGE_DAYS", "7"))  # Cleanup runs older than N days
_SAFE_WORKFLOW_ERRORS = {
    "Missing AZURE_OPENAI_ENDPOINT",
    "Missing AZURE_OPENAI_CHAT_DEPLOYMENT_NAME or AZURE_OPENAI_CHAT_MODEL",
}


def _cleanup_stale_runs() -> None:
    """Remove runs older than _STALE_RUN_MAX_AGE_DAYS from memory.
    
    This prevents memory leaks from long-running server instances.
    Runs are stored in memory, so old runs should be pruned periodically.
    """
    cutoff_time = datetime.utcnow() - timedelta(days=_STALE_RUN_MAX_AGE_DAYS)
    stale_run_ids = []
    
    for run_id, run_info in _active_runs.items():
        started_at_str = run_info.get("started_at", "")
        if not started_at_str:
            continue
        
        try:
            started_at = datetime.fromisoformat(started_at_str)
            if started_at < cutoff_time:
                stale_run_ids.append(run_id)
        except (ValueError, TypeError):
            # Malformed timestamp, skip
            continue
    
    for run_id in stale_run_ids:
        del _active_runs[run_id]
    
    if stale_run_ids:
        logger.info("Cleaned up %d stale runs (older than %d days)", 
                   len(stale_run_ids), _STALE_RUN_MAX_AGE_DAYS)
    else:
        logger.debug("No stale runs to clean up")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager: startup and shutdown logic.
    
    Replaces deprecated @app.on_event("startup"/"shutdown") decorators.
    Runs once when server starts, and cleanup code runs when server stops.
    
    See: https://fastapi.tiangolo.com/advanced/events/#alternative-events-deprecated
    """
    # ========== STARTUP ==========
    global _config
    _config = WorkflowConfig.from_env()
    
    # Validate Azure OpenAI config
    config_error = _config.validate()
    if config_error:
        logger.warning(
            "Missing Azure OpenAI configuration. %s. "
            "Please set the required values in .env",
            config_error,
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
    
    # Clean up stale runs from previous server instances
    _cleanup_stale_runs()
    
    yield  # Server runs here
    
    # ========== SHUTDOWN ==========
    logger.info("HITL Dashboard shutting down")
    # Optional: Add cleanup code here (close connections, flush logs, etc.)
    # For now, nothing additional needed


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="HITL Demo Dashboard",
    description="Human-In-The-Loop demonstration workflows",
    version="1.0.0",
    lifespan=lifespan
)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Keep submitted values out of validation error responses."""
    return JSONResponse(status_code=422, content={"detail": "Invalid request."})



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
            input_placeholder="Enter content to review...",
            email_notifications_supported="sequential" in _EMAIL_NOTIFICATION_WORKFLOWS,
        ),
        WorkflowMetadata(
            id="concurrent",
            name="Concurrent",
            description="Multi-perspective analysis with concurrent agents and approval",
            input_required=True,
            input_placeholder="Enter topic to analyze...",
            email_notifications_supported="concurrent" in _EMAIL_NOTIFICATION_WORKFLOWS,
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
            input_placeholder="Enter discussion topic...",
            email_notifications_supported="group_chat" in _EMAIL_NOTIFICATION_WORKFLOWS,
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
async def start_workflow(
    workflow_id: str,
    body: StartWorkflowRequest,
) -> dict[str, Any]:
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
    input_text = body.input
    
    if workflow_id in _TOPIC_REQUIRED and not str(input_text).strip():
        raise HTTPException(status_code=400, detail="A topic is required for this workflow")

    if body.email_notifications:
        if workflow_id not in _EMAIL_NOTIFICATION_WORKFLOWS:
            raise HTTPException(status_code=422, detail="Email notifications are not supported for this workflow")
        if _config is None:
            raise HTTPException(status_code=503, detail="Email notifications are not configured")
        try:
            validate_smtp_config(_config)
        except ValueError as exc:
            raise HTTPException(
                status_code=503,
                detail="Email notifications require SMTP_USER, SMTP_PASSWORD, and a recipient",
            ) from exc

    _active_runs[run_id] = {
        "workflow_id": workflow_id,
        "input": input_text,
        "email_notifications": body.email_notifications,
        "started_at": datetime.utcnow().isoformat(),
        "status": "running",
        "pending_requests": {},  # Requests currently awaiting a human response
        "waiters": {},  # request_id -> Future resolved by the approve/input endpoints
    }
    
    logger.info("Started workflow %s with run_id %s", workflow_id, run_id)
    return {"run_id": run_id, "status": "started"}


@app.post("/api/workflows/{workflow_id}/approve")
async def submit_approval(
    workflow_id: str,
    body: ApprovalRequest,
) -> dict[str, Any]:
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
    run_info = _active_runs.get(body.run_id)
    if run_info is None or run_info["workflow_id"] != workflow_id:
        raise HTTPException(status_code=404, detail="Run not found")

    pending_request = run_info["pending_requests"].get(body.request_id)
    if pending_request is None or pending_request["kind"] not in {
        "approval",
        "approval_batch",
    }:
        raise HTTPException(status_code=409, detail="Approval request is not pending")

    decision_ids = pending_request["decision_ids"]
    if pending_request["kind"] == "approval_batch":
        if set(body.decisions) != decision_ids:
            raise HTTPException(
                status_code=422,
                detail="A decision is required for every item in the approval batch",
            )
    elif body.decisions:
        raise HTTPException(status_code=422, detail="Unexpected batch decisions")

    _deliver_response(
        body.run_id,
        body.request_id,
        {
            "type": "approval",
            "approved": body.approved,
            "feedback": body.feedback,
            "decisions": body.decisions,
        },
    )
    
    logger.info(
        "Approval submitted for run %s request %s: %s",
        body.run_id,
        body.request_id,
        body.approved,
    )
    return {"status": "accepted"}


@app.post("/api/workflows/{workflow_id}/input")
async def submit_input(
    workflow_id: str,
    body: InputRequest,
) -> dict[str, Any]:
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
    run_info = _active_runs.get(body.run_id)
    if run_info is None or run_info["workflow_id"] != workflow_id:
        raise HTTPException(status_code=404, detail="Run not found")

    pending_request = run_info["pending_requests"].get(body.request_id)
    if pending_request is None or pending_request["kind"] != "input":
        raise HTTPException(status_code=409, detail="Input request is not pending")

    _deliver_response(
        body.run_id,
        body.request_id,
        {
            "type": "input",
            "input": body.input,
        },
    )
    
    logger.info(
        "Input submitted for run %s request %s",
        body.run_id,
        body.request_id,
    )
    return {"status": "accepted"}


# ============================================================================
# Helper Functions
# ============================================================================

def _deliver_response(run_id: str, request_id: str, response: dict[str, Any]) -> None:
    """Hand a human's response to the workflow that is waiting on it."""
    run_info = _active_runs[run_id]
    waiter = run_info["waiters"].get(request_id)
    if waiter is None or waiter.done():
        raise HTTPException(status_code=409, detail="Request is not awaiting a response")
    waiter.set_result(response)


async def _watch_disconnect(websocket: WebSocket) -> None:
    """Return when the client goes away (the dashboard sends no messages of its own)."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


async def _send_output(
    websocket: WebSocket, run_info: dict[str, Any], agent: str, content: str, severity: str = "info",
) -> None:
    """Send and record a dashboard output message for later notifications."""
    await websocket.send_json({
        "type": "agent_message",
        "timestamp": datetime.utcnow().isoformat(),
        "agent_name": agent,
        "content": content,
        "severity": severity,
    })
    if "workflow_output" in run_info:
        run_info["workflow_output"].append(f"{agent}:\n{content}")


async def _request_response(
    websocket: WebSocket,
    run_id: str,
    request_id: str,
    response_kind: Literal["approval", "approval_batch", "input"],
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
    run_info["pending_requests"][request_id] = {
        "kind": response_kind,
        "decision_ids": {
            item["request_id"]
            for item in payload.get("items", [])
            if isinstance(item, dict) and isinstance(item.get("request_id"), str)
        },
    }
    disconnect_task = asyncio.ensure_future(_watch_disconnect(websocket))
    try:
        notification_status = None
        if run_info.get("email_notifications", False):
            try:
                if _config is None:
                    raise ValueError("Email configuration is not available")
                email_payload = payload
                if "workflow_output" in run_info:
                    email_payload = {
                        **payload,
                        "workflow_output": "\n\n".join(run_info["workflow_output"]),
                    }
                await asyncio.to_thread(
                    send_notification_email, _config, run_info["workflow_id"], response_kind, email_payload
                )
                notification_status = "sent"
                await _send_output(
                    websocket, run_info, "system",
                    "Email notification sent to the configured mail server. Check your email and respond in the dashboard.",
                )
            except (OSError, smtplib.SMTPException, ValueError) as exc:
                notification_status = "failed"
                logger.warning(
                    "Email notification failed (exception_type=%s)", type(exc).__name__
                )
                await _send_output(
                    websocket, run_info, "system",
                    "Email notification failed. Please respond in the dashboard.", "warning",
                )
        await websocket.send_json({**payload, "email_notification": notification_status})
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
        run_info["pending_requests"].pop(request_id, None)
        if not waiter.done():
            waiter.cancel()
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
        if run_info.get("email_notifications", False):
            run_info["workflow_output"] = [
                "system:\nWorkflow starting...",
                f"system:\nStarting {workflow_id} workflow...",
            ]
        
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
        
        logger.info("Starting workflow execution for %s", workflow_id)
        
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
            elif workflow_id == "handoff":
                # Agent Framework Handoff pattern: takes user query/issue
                query = user_input or "I need technical support with my API integration."
                workflow_stream = workflow_runner(_config, query)
            elif workflow_id == "magentic":
                # Agent Framework Magentic pattern: takes task/analysis request
                task = user_input or "Analyze market trends in cloud infrastructure."
                workflow_stream = workflow_runner(_config, task)
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
                    
                    await _send_output(websocket, run_info, agent_name, content)
                
                # Send approval requests and wait for the human's decision
                elif event_type == "approval_required":
                    data = event_data if isinstance(event_data, dict) else {}
                    request_id = data.get("request_id", str(uuid.uuid4()))
                    
                    reply = await _request_response(
                        websocket,
                        run_id,
                        request_id,
                        "approval",
                        {
                            "type": "approval_required",
                            "timestamp": datetime.utcnow().isoformat(),
                            "request_id": request_id,
                            "prompt": data.get("prompt", "Approve?"),
                            "content": data.get("content", ""),
                            "email_context": data.get("email_context", ""),
                            "agent_name": data.get("agent", ""),
                            "severity": "info",
                        },
                    )
                    if reply is None:
                        reply = {"type": "approval", "approved": False, "feedback": "timed out"}
                        await _send_output(
                            websocket, run_info, "system",
                            "No response received within 5 minutes; treated as rejected.", "warning",
                        )
                    else:
                        await _send_output(
                            websocket, run_info, "system",
                            "✓ Response approved" if reply.get("approved") else "✗ Response rejected",
                        )
                
                # Send a batch of items to approve individually (one modal, one decision each)
                elif event_type == "approval_batch":
                    data = event_data if isinstance(event_data, dict) else {}
                    request_id = data.get("request_id", str(uuid.uuid4()))
                    
                    reply = await _request_response(
                        websocket,
                        run_id,
                        request_id,
                        "approval_batch",
                        {
                            "type": "approval_batch",
                            "timestamp": datetime.utcnow().isoformat(),
                            "request_id": request_id,
                            "prompt": data.get("prompt", "Review each item"),
                            "items": data.get("items", []),
                            "email_context": data.get("email_context", ""),
                            "severity": "info",
                        },
                    )
                    if reply is None:
                        await _send_output(
                            websocket, run_info, "system",
                            "No response received within 5 minutes; unreviewed responses will be rejected.",
                            "warning",
                        )
                    else:
                        decisions = reply.get("decisions", {})
                        approved = sum(decisions.values())
                        await _send_output(
                            websocket, run_info, "system",
                            f"{approved} of {len(decisions)} responses approved",
                        )
                
                # Send input requests and wait for the human's text
                elif event_type == "input_required":
                    data = event_data if isinstance(event_data, dict) else {}
                    request_id = data.get("request_id", str(uuid.uuid4()))
                    
                    reply = await _request_response(
                        websocket,
                        run_id,
                        request_id,
                        "input",
                        {
                            "type": "input_required",
                            "timestamp": datetime.utcnow().isoformat(),
                            "request_id": request_id,
                            "prompt": data.get("prompt", "Enter input:"),
                            "content": data.get("content", ""),
                            "email_context": data.get("email_context", ""),
                            "options": data.get("options", []),
                            "agent_name": data.get("agent", ""),
                            "severity": "info",
                        },
                    )
                    if reply is None:
                        reply = {"type": "input", "input": ""}
                        await _send_output(
                            websocket, run_info, "system",
                            "No response received within 5 minutes; continuing without input.", "warning",
                        )
                
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
                    error_message = (
                        event_data.get("message")
                        if isinstance(event_data, dict)
                        else None
                    )
                    if (
                        not isinstance(error_message, str)
                        or error_message not in _SAFE_WORKFLOW_ERRORS
                    ):
                        error_message = "Workflow failed. Check server logs."
                    await websocket.send_json({
                        "type": "error",
                        "timestamp": datetime.utcnow().isoformat(),
                        "content": error_message,
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
            logger.error(
                "Workflow execution failed for %s (exception_type=%s)",
                workflow_id,
                type(e).__name__,
            )
            await websocket.send_json({
                "type": "error",
                "content": "Workflow failed. Check server logs.",
                "severity": "error",
            })
            run_info["status"] = "error"
        
        finally:
            run_info.pop("workflow_output", None)
            if agen is not None:
                await agen.aclose()
        
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for workflow %s run %s", workflow_id, run_id)
    except Exception as e:
        logger.error(
            "WebSocket handler failed for workflow %s (exception_type=%s)",
            workflow_id,
            type(e).__name__,
        )
        try:
            await websocket.send_json({
                "type": "error",
                "content": "Workflow failed. Check server logs.",
                "severity": "error",
            })
        except Exception as send_error:
            logger.debug(
                "Could not send WebSocket error response (exception_type=%s)",
                type(send_error).__name__,
            )


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

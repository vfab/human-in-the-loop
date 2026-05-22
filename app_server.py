"""HITL Workflow HTTP Server.

Exposes all five Human-in-the-Loop workflow samples behind a REST API so they
can be driven from a browser dashboard.

Backward-compatible: the original POST /run endpoint is preserved.
"""

import asyncio
import logging
import os
import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_framework import (
    AgentExecutorResponse,
    Message,
    WorkflowBuilder,
    WorkflowEvent,
    WorkflowRunState,
)
from agent_framework_openai import OpenAIChatClient, OpenAIChatCompletionClient
from agent_framework_orchestrations import (
    AgentRequestInfoResponse,
    ConcurrentBuilder,
    SequentialBuilder,
)
from email_delivery import send_email_via_acs
from guessing_game_with_human_input import (
    HumanFeedbackRequest,
    TurnManager,
    create_guessing_agent,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="HITL Workflow Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://happy-desert-082ae9403.7.azurestaticapps.net",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Legacy /run endpoint  (preserved for backward compatibility)
# ─────────────────────────────────────────────────────────────────────────────

from dataclasses import dataclass


@dataclass
class _LegacyEmail:
    sender: str
    subject: str
    body: str

    def __str__(self) -> str:
        return f"From: {self.sender}\nSubject: {self.subject}\n\n{self.body}"


class EmailRequest(BaseModel):
    sender: str
    subject: str
    body: str


class _LegacyEmailAssistant:
    def __init__(self, chat_client: OpenAIChatClient) -> None:
        self.agent = chat_client.as_agent(
            name="Email Writer",
            instructions=(
                "You are an excellent email assistant. "
                "Respond to incoming emails professionally and concisely."
            ),
        )

    async def process_email(self, email: _LegacyEmail) -> str:
        message = str(email)
        if email.sender == "sam@example.com":
            message = "IMPORTANT EMAIL FROM KEY TEAM MEMBER.\n\n" + message
        result = await self.agent.run(message)
        return result.text


_legacy_assistant = _LegacyEmailAssistant(OpenAIChatClient())
# Public alias kept for backward compatibility with tests
assistant = _legacy_assistant


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
async def run_workflow_legacy(request: EmailRequest) -> dict[str, str]:
    email = _LegacyEmail(sender=request.sender, subject=request.subject, body=request.body)
    try:
        result = await _legacy_assistant.process_email(email)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error processing email: {exc}") from exc
    return {"response": result}


# ─────────────────────────────────────────────────────────────────────────────
# Session store
# ─────────────────────────────────────────────────────────────────────────────

_MAX_RUNS = 50


class WorkflowRun:
    """Represents an active or completed HITL workflow execution."""

    def __init__(self, run_id: str, workflow_name: str) -> None:
        self.run_id = run_id
        self.workflow_name = workflow_name
        self.status: Literal["running", "waiting_input", "completed", "error"] = "running"
        self.messages: list[dict] = []
        self.pending_request_id: str | None = None
        self.pending_prompt: str | None = None
        self.pending_agent: str | None = None
        self.result: str | None = None
        self.error: str | None = None
        self._human_response: str | None = None
        self._response_ready = asyncio.Event()


_runs: dict[str, WorkflowRun] = {}


def _new_run(workflow_name: str) -> WorkflowRun:
    run = WorkflowRun(run_id=str(uuid.uuid4()), workflow_name=workflow_name)
    if len(_runs) >= _MAX_RUNS:
        del _runs[next(iter(_runs))]
    _runs[run.run_id] = run
    return run


def _run_to_dict(run: WorkflowRun) -> dict:
    return {
        "run_id": run.run_id,
        "workflow": run.workflow_name,
        "status": run.status,
        "messages": list(run.messages),
        "pending": (
            {
                "request_id": run.pending_request_id,
                "prompt": run.pending_prompt,
                "agent": run.pending_agent,
            }
            if run.status == "waiting_input"
            else None
        ),
        "result": run.result,
        "error": run.error,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chat client factory
# ─────────────────────────────────────────────────────────────────────────────

def _create_openai_client() -> OpenAIChatCompletionClient:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    model = os.getenv("AZURE_OPENAI_CHAT_MODEL") or os.getenv("AZURE_OPENAI_MODEL")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = "2024-12-01-preview"
    if not endpoint or not model:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_MODEL must be set")
    if api_key:
        return OpenAIChatCompletionClient(
            model=model, azure_endpoint=endpoint, api_version=api_version, api_key=api_key
        )
    from azure.identity import DefaultAzureCredential  # noqa: PLC0415
    return OpenAIChatCompletionClient(
        model=model,
        azure_endpoint=endpoint,
        api_version=api_version,
        credential=DefaultAzureCredential(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Event data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_request_prompt(event_data: Any) -> str:
    """Human-readable prompt shown in the browser when a workflow pauses."""
    if isinstance(event_data, HumanFeedbackRequest):
        return event_data.prompt
    if hasattr(event_data, "agent_response") and event_data.agent_response:
        return getattr(event_data.agent_response, "text", None) or "Agent response ready for review."
    return "Human input required."


def _extract_agent_text(event_data: Any) -> str:
    """The agent's visible output from a request_info event payload."""
    if isinstance(event_data, HumanFeedbackRequest):
        return ""
    if hasattr(event_data, "agent_response") and event_data.agent_response:
        return getattr(event_data.agent_response, "text", None) or ""
    return ""


def _extract_output_text(data: Any) -> str:
    if data is None:
        return ""
    if hasattr(data, "text"):
        return data.text or ""
    if isinstance(data, list):
        return "".join(item.text for item in data if hasattr(item, "text") and item.text)
    return str(data)


def _safe_source_id(event: Any) -> str:
    """Return the source executor ID without raising if the property is unavailable."""
    try:
        return event.source_executor_id or "agent"
    except Exception:  # noqa: BLE001
        return "agent"


# ─────────────────────────────────────────────────────────────────────────────
# Generic HITL event loop
# ─────────────────────────────────────────────────────────────────────────────

async def _hitl_loop(
    run: WorkflowRun,
    workflow: Any,
    initial_message: str,
    *,
    use_raw_responses: bool = False,
) -> None:
    """
    Drive a workflow to completion, pausing at every request_info event.

    When the workflow emits request_info the loop suspends and sets
    run.status = "waiting_input". The /respond endpoint unblocks it by
    setting run._response_ready.

    use_raw_responses=True sends the human's string directly as the response
    value (required by WorkflowBuilder / guessing-game); otherwise wraps in
    AgentRequestInfoResponse.
    """
    pending_responses: dict | None = None

    try:
        while run.status not in ("completed", "error"):
            stream = (
                workflow.run(responses=pending_responses, stream=True)
                if pending_responses is not None
                else workflow.run(initial_message, stream=True)
            )
            pending_responses = None
            seen_event = False

            async for event in stream:
                seen_event = True
                if not isinstance(event, WorkflowEvent):
                    continue

                if event.type == "request_info":
                    agent_id = _safe_source_id(event)
                    prompt = _extract_request_prompt(event.data)
                    agent_text = _extract_agent_text(event.data)

                    if agent_text:
                        run.messages.append(
                            {"role": "agent", "author": agent_id, "content": agent_text}
                        )

                    run.pending_request_id = event.request_id
                    run.pending_prompt = prompt
                    run.pending_agent = agent_id
                    run.status = "waiting_input"

                    # Suspend until the /respond endpoint unblocks us.
                    await run._response_ready.wait()
                    run._response_ready.clear()

                    human_response = run._human_response or ""
                    run.pending_request_id = None
                    run.pending_prompt = None
                    run.pending_agent = None
                    run.status = "running"

                    run.messages.append(
                        {
                            "role": "human",
                            "author": "you",
                            "content": human_response if human_response else "(approved)",
                        }
                    )

                    if use_raw_responses:
                        pending_responses = {event.request_id: human_response}
                    elif not human_response:
                        pending_responses = {event.request_id: AgentRequestInfoResponse.approve()}
                    else:
                        pending_responses = {
                            event.request_id: AgentRequestInfoResponse.from_strings([human_response])
                        }
                    # Stream ends naturally after request_info; outer loop restarts with responses.

                elif event.type == "output":
                    text = _extract_output_text(event.data)
                    if text:
                        author = _safe_source_id(event)
                        # Accumulate streaming tokens from the same agent into one bubble.
                        if (
                            run.messages
                            and run.messages[-1]["role"] == "agent"
                            and run.messages[-1]["author"] == author
                        ):
                            run.messages[-1]["content"] += text
                        else:
                            run.messages.append({"role": "agent", "author": author, "content": text})

                elif event.type == "status" and getattr(event, "state", None) == WorkflowRunState.IDLE:
                    run.status = "completed"

            if not seen_event and pending_responses is None:
                run.status = "completed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("Workflow %s failed", run.workflow_name)
        run.error = str(exc)
        run.status = "error"


# ─────────────────────────────────────────────────────────────────────────────
# Workflow starter coroutines
# ─────────────────────────────────────────────────────────────────────────────

async def _run_sequential(run: WorkflowRun, topic: str) -> None:
    client = _create_openai_client()
    drafter = client.as_agent(
        name="drafter",
        instructions="You are a document drafter. Write a concise draft (2-3 sentences) for the given topic.",
    )
    editor = client.as_agent(
        name="editor",
        instructions=(
            "You are an editor. Improve the draft for clarity and impact. "
            "Incorporate any human feedback provided."
        ),
    )
    workflow = (
        SequentialBuilder(participants=[drafter, editor])
        .with_request_info(agents=["editor"])
        .build()
    )
    await _hitl_loop(run, workflow, topic)


async def _run_concurrent(run: WorkflowRun, topic: str) -> None:
    client = _create_openai_client()
    technical = client.as_agent(
        name="technical_analyst",
        instructions=(
            "You are a technical analyst. Provide a technical perspective on implementation, "
            "performance, and architecture. Keep to 2-3 sentences."
        ),
    )
    business = client.as_agent(
        name="business_analyst",
        instructions=(
            "You are a business analyst. Provide a business perspective on ROI, "
            "market impact, and strategic value. Keep to 2-3 sentences."
        ),
    )
    ux = client.as_agent(
        name="ux_analyst",
        instructions=(
            "You are a UX analyst. Provide a UX perspective on usability, "
            "accessibility, and satisfaction. Keep to 2-3 sentences."
        ),
    )

    async def aggregate(results: list[AgentExecutorResponse]) -> str:
        parts: list[str] = []
        for r in results:
            msgs = getattr(getattr(r, "agent_response", None), "messages", [])
            text = msgs[-1].text if msgs else "(no content)"
            parts.append(f"{getattr(r, 'executor_id', 'analyst')}:\n{text}")
        sys_msg = Message(
            "system",
            ["Consolidate the following analyst perspectives into one cohesive summary (3-4 sentences)."],
        )
        usr_msg = Message("user", ["\n\n".join(parts)])
        resp = await client.get_response([sys_msg, usr_msg])
        return resp.messages[-1].text if resp.messages else ""

    workflow = (
        ConcurrentBuilder(participants=[technical, business, ux])
        .with_aggregator(aggregate)
        .with_request_info(agents=["technical_analyst"])
        .build()
    )
    await _hitl_loop(run, workflow, topic)


async def _run_group_chat(run: WorkflowRun, topic: str) -> None:
    client = _create_openai_client()
    optimist = client.as_agent(
        name="optimist",
        instructions=(
            "You are an optimistic team member. See opportunities and build on others' points. "
            "Keep to 2-3 sentences."
        ),
    )
    pragmatist = client.as_agent(
        name="pragmatist",
        instructions=(
            "You are a pragmatic team member. Focus on practical implementation and realistic timelines. "
            "Keep to 2-3 sentences."
        ),
    )
    creative = client.as_agent(
        name="creative",
        instructions=(
            "You are a creative team member. Propose innovative, unconventional solutions. "
            "Keep to 2-3 sentences."
        ),
    )
    workflow = (
        SequentialBuilder(participants=[optimist, pragmatist, creative])
        .with_request_info(agents=["pragmatist"])
        .build()
    )
    await _hitl_loop(run, workflow, topic)


async def _run_guessing_game(run: WorkflowRun) -> None:
    run.messages.append(
        {
            "role": "system",
            "author": "system",
            "content": (
                "Think of a number between 1 and 100. "
                "The agent will guess — respond: higher, lower, much higher, much lower, or correct."
            ),
        }
    )
    guessing_agent = create_guessing_agent()
    turn_manager = TurnManager(id="turn_manager")
    workflow = (
        WorkflowBuilder(start_executor=turn_manager)
        .add_edge(turn_manager, guessing_agent)
        .add_edge(guessing_agent, turn_manager)
    ).build()
    await _hitl_loop(run, workflow, "start", use_raw_responses=True)


async def _run_invoice_approval(
    run: WorkflowRun,
    vendor: str,
    amount: float,
    invoice_date_str: str,
) -> None:
    """Generate a mock invoice then auto-approve or escalate based on App Config rules."""
    from datetime import date  # noqa: PLC0415

    from invoice_workflow import InvoiceConfig, evaluate_invoice, load_invoice_config  # noqa: PLC0415

    try:
        # Parse and default the invoice date
        if invoice_date_str:
            try:
                invoice_date = date.fromisoformat(invoice_date_str)
            except ValueError:
                run.error = f"Invalid date '{invoice_date_str}'. Use YYYY-MM-DD."
                run.status = "error"
                return
        else:
            invoice_date = date.today()
            invoice_date_str = invoice_date.isoformat()

        config: InvoiceConfig = load_invoice_config()

        run.messages.append({
            "role": "system", "author": "system",
            "content": (
                f"Processing invoice — Vendor: {vendor}, "
                f"Amount: ${amount:,.2f}, Date: {invoice_date_str}"
            ),
        })

        # AI agent generates a realistic invoice document
        client = _create_openai_client()
        agent = client.as_agent(
            name="Invoice Agent",
            instructions=(
                "You are an invoice processing assistant. "
                "Generate a professional, realistic invoice document. "
                "Include: invoice number (INV-XXXXX format), vendor name and address, "
                "bill-to details, itemised line items whose subtotals match the total, "
                "payment terms (Net-30), and a brief description of services rendered. "
                "Format the output as a clean plain-text invoice."
            ),
        )
        response = await agent.run(
            f"Generate a professional invoice:\n"
            f"- Vendor: {vendor}\n"
            f"- Total Amount: ${amount:,.2f}\n"
            f"- Invoice Date: {invoice_date_str}\n"
            f"- Bill To: Contoso Ltd., 123 Enterprise Blvd, Seattle WA 98101"
        )
        invoice_text = response.text
        run.messages.append({"role": "agent", "author": "Invoice Agent", "content": invoice_text})

        # Evaluate auto-approval conditions deterministically
        eval_result = evaluate_invoice(vendor, amount, invoice_date, config)

        if eval_result["can_auto_approve"]:
            run.messages.append({
                "role": "system", "author": "system",
                "content": (
                    f"✓ Auto-approved: vendor is recognised, "
                    f"amount is within the ${config.cost_limit:,.0f} limit, "
                    f"and invoice is within the {config.days_limit}-day window."
                ),
            })
            run.result = f"Invoice auto-approved — ${amount:,.2f} from {vendor}."
            run.status = "completed"
        else:
            reasons_text = "; ".join(eval_result["reasons"])
            run.messages.append({
                "role": "system", "author": "system",
                "content": f"Manual review required: {reasons_text}.",
            })

            run.pending_request_id = str(uuid.uuid4())
            run.pending_prompt = (
                f"Review required:\n• {chr(10).join('• ' + r for r in eval_result['reasons'])}\n\n"
                "Approve or reject this invoice?"
            )
            run.pending_agent = "Invoice Agent"
            run.status = "waiting_input"

            await run._response_ready.wait()
            run._response_ready.clear()

            decision = (run._human_response or "").strip().lower()
            run.pending_request_id = None
            run.pending_prompt = None
            run.pending_agent = None
            run.status = "running"

            run.messages.append({
                "role": "human", "author": "you",
                "content": run._human_response or "(approved)",
            })

            if decision in ("reject", "rejected", "no", "deny", "denied"):
                run.messages.append({
                    "role": "system", "author": "system",
                    "content": "Invoice rejected by reviewer. Not processed.",
                })
                run.result = f"Invoice rejected — ${amount:,.2f} from {vendor}."
            else:
                note = (
                    f" — Note: {run._human_response}"
                    if run._human_response and decision not in ("approve", "approved", "yes", "ok")
                    else ""
                )
                run.messages.append({
                    "role": "system", "author": "system",
                    "content": f"Invoice approved by reviewer.{note}",
                })
                run.result = f"Invoice approved — ${amount:,.2f} from {vendor}."

            run.status = "completed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("Invoice approval workflow failed")
        run.error = str(exc)
        run.status = "error"


async def _run_support_ticket(
    run: WorkflowRun,
    customer: str,
    issue: str,
) -> None:
    """Classify a support ticket and auto-resolve simple cases; escalate the rest."""
    from support_ticket_workflow import (  # noqa: PLC0415
        TICKET_CATEGORIES,
        detect_escalation_keywords,
        load_support_config,
        parse_agent_classification,
    )

    try:
        config = load_support_config()

        snippet = issue[:80] + ("…" if len(issue) > 80 else "")
        run.messages.append({
            "role": "system", "author": "system",
            "content": f"Support ticket received from {customer}: {snippet}",
        })

        # AI agent classifies and drafts a resolution
        client = _create_openai_client()
        categories_list = ", ".join(TICKET_CATEGORIES.keys())
        agent = client.as_agent(
            name="Support Agent",
            instructions=(
                "You are a customer support AI. Analyse the support ticket and respond "
                "using this exact format (no extra text before CATEGORY):\n\n"
                f"CATEGORY: <one of: {categories_list}>\n"
                "COMPLEXITY: <integer 1-5 where 1=trivial, 5=very complex>\n"
                "RESOLUTION:\n"
                "<your full resolution response addressed directly to the customer>"
            ),
        )
        response = await agent.run(f"Customer: {customer}\nIssue: {issue}")
        ai_output = response.text

        category, complexity, resolution = parse_agent_classification(ai_output)
        cat_label = TICKET_CATEGORIES.get(category, category)

        run.messages.append({
            "role": "agent", "author": "Support Agent",
            "content": (
                f"Category: {cat_label}\n"
                f"Complexity: {complexity}/5\n\n"
                f"Proposed resolution:\n{resolution}"
            ),
        })

        # Determine routing
        escalation_hits = detect_escalation_keywords(issue, config)
        needs_human = (
            category not in config["auto_resolve_categories"]
            or complexity > 2
            or len(escalation_hits) > 0
        )

        if not needs_human:
            run.messages.append({
                "role": "system", "author": "system",
                "content": (
                    f"✓ Auto-resolved: '{cat_label}' tickets are handled automatically "
                    f"(complexity {complexity}/5)."
                ),
            })
            run.result = f"Ticket auto-resolved for {customer}."
            run.status = "completed"
        else:
            triggers: list[str] = []
            if category not in config["auto_resolve_categories"]:
                triggers.append(f"category '{cat_label}' requires human handling")
            if complexity > 2:
                triggers.append(f"complexity rated {complexity}/5")
            if escalation_hits:
                triggers.append(f"escalation keywords detected: {', '.join(escalation_hits)}")

            reason_text = "; ".join(triggers)
            run.messages.append({
                "role": "system", "author": "system",
                "content": f"Escalated to human: {reason_text}.",
            })

            run.pending_request_id = str(uuid.uuid4())
            run.pending_prompt = (
                f"Escalated — {reason_text}\n\n"
                "Approve the AI resolution, or type a custom response to send to the customer."
            )
            run.pending_agent = "Support Agent"
            run.status = "waiting_input"

            await run._response_ready.wait()
            run._response_ready.clear()

            custom = (run._human_response or "").strip()
            run.pending_request_id = None
            run.pending_prompt = None
            run.pending_agent = None
            run.status = "running"

            run.messages.append({
                "role": "human", "author": "you",
                "content": custom if custom else "(approved AI resolution)",
            })
            final_response = custom if custom else resolution
            run.messages.append({
                "role": "system", "author": "system",
                "content": f"Resolution sent to {customer}.",
            })
            run.result = f"Ticket resolved for {customer} (human-reviewed)."
            run.status = "completed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("Support ticket workflow failed")
        run.error = str(exc)
        run.status = "error"


async def _run_email_approval(
    run: WorkflowRun,
    sender: str,
    subject: str,
    body: str,
) -> None:
    """Two-phase: generate draft then wait for human approval, then send or reject."""
    try:
        client = _create_openai_client()
        agent = client.as_agent(
            name="Email Writer",
            instructions=(
                "You are a professional email assistant. "
                "Draft a clear, concise reply to the incoming email."
            ),
        )
        incoming = f"From: {sender}\nSubject: {subject}\n\n{body}"
        if sender == "sam@example.com":
            incoming = "IMPORTANT EMAIL FROM KEY TEAM MEMBER\n\n" + incoming

        run.messages.append(
            {"role": "system", "author": "system", "content": f"Processing email from {sender}: {subject}"}
        )

        response = await agent.run(incoming)
        draft = response.text
        run.messages.append({"role": "agent", "author": "Email Writer", "content": draft})

        run.pending_request_id = str(uuid.uuid4())
        run.pending_prompt = draft
        run.pending_agent = "Email Writer"
        run.status = "waiting_input"

        await run._response_ready.wait()
        run._response_ready.clear()

        decision = (run._human_response or "").strip()
        run.pending_request_id = None
        run.pending_prompt = None
        run.pending_agent = None
        run.status = "running"

        recipient = os.getenv("EMAIL_RECIPIENT", "vince@nimblegravity.com")

        if decision.lower() == "reject":
            run.messages.append(
                {"role": "system", "author": "system", "content": "Email rejected. Not sent."}
            )
            run.result = "Email rejected by reviewer."
        else:
            final_body = draft if decision.lower() == "approve" else decision
            send_email_via_acs(subject=f"Re: {subject}", body=final_body, recipient=recipient)
            run.messages.append(
                {"role": "system", "author": "system", "content": f"Email sent to {recipient}."}
            )
            run.result = f"Email sent to {recipient}."

        run.status = "completed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("Email approval workflow failed")
        run.error = str(exc)
        run.status = "error"


# ─────────────────────────────────────────────────────────────────────────────
# HTTP request/response models
# ─────────────────────────────────────────────────────────────────────────────

class StartSequentialReq(BaseModel):
    topic: str = "Write a brief introduction to artificial intelligence."


class StartConcurrentReq(BaseModel):
    topic: str = "Analyze the impact of large language models on software development."


class StartGroupChatReq(BaseModel):
    topic: str = "Discuss how our team should approach adopting AI tools for productivity."


class StartEmailApprovalReq(BaseModel):
    sender: str = "sam@example.com"
    subject: str = "Urgent: Agent Framework Review Required"
    body: str = (
        "Please review the latest agent framework updates and provide your feedback. "
        "This is critical for our Q4 roadmap."
    )


class StartInvoiceApprovalReq(BaseModel):
    vendor: str = "Microsoft"
    amount: float = 750.0
    invoice_date: str = ""  # YYYY-MM-DD; empty defaults to today


class StartSupportTicketReq(BaseModel):
    customer: str = "Alice Johnson"
    issue: str = (
        "I can't log into my account. "
        "I've tried resetting my password three times but keep getting an error."
    )


class RespondReq(BaseModel):
    response: str


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    frontend = Path(__file__).parent / "frontend" / "index.html"
    if frontend.exists():
        return FileResponse(frontend, media_type="text/html")
    return {
        "name": "HITL Workflow Server",
        "version": "2.0.0",
        "workflows": ["sequential", "concurrent", "group-chat", "guessing-game", "email-approval"],
        "endpoints": ["POST /run", "POST /workflows/{wf}/start", "GET /workflows/{run_id}", "POST /workflows/{run_id}/respond"],
    }


@app.post("/workflows/sequential/start")
async def start_sequential(req: StartSequentialReq) -> dict:
    run = _new_run("sequential")
    asyncio.create_task(_run_sequential(run, req.topic))
    return _run_to_dict(run)


@app.post("/workflows/concurrent/start")
async def start_concurrent(req: StartConcurrentReq) -> dict:
    run = _new_run("concurrent")
    asyncio.create_task(_run_concurrent(run, req.topic))
    return _run_to_dict(run)


@app.post("/workflows/group-chat/start")
async def start_group_chat(req: StartGroupChatReq) -> dict:
    run = _new_run("group-chat")
    asyncio.create_task(_run_group_chat(run, req.topic))
    return _run_to_dict(run)


@app.post("/workflows/guessing-game/start")
async def start_guessing_game() -> dict:
    run = _new_run("guessing-game")
    asyncio.create_task(_run_guessing_game(run))
    return _run_to_dict(run)


@app.post("/workflows/email-approval/start")
async def start_email_approval(req: StartEmailApprovalReq) -> dict:
    run = _new_run("email-approval")
    asyncio.create_task(_run_email_approval(run, req.sender, req.subject, req.body))
    return _run_to_dict(run)


@app.post("/workflows/invoice-approval/start")
async def start_invoice_approval(req: StartInvoiceApprovalReq) -> dict:
    run = _new_run("invoice-approval")
    asyncio.create_task(_run_invoice_approval(run, req.vendor, req.amount, req.invoice_date))
    return _run_to_dict(run)


@app.post("/workflows/support-ticket/start")
async def start_support_ticket(req: StartSupportTicketReq) -> dict:
    run = _new_run("support-ticket")
    asyncio.create_task(_run_support_ticket(run, req.customer, req.issue))
    return _run_to_dict(run)


@app.get("/workflows/{run_id}")
async def get_run(run_id: str) -> dict:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_dict(run)


@app.post("/workflows/{run_id}/respond")
async def respond_to_run(run_id: str, req: RespondReq) -> dict:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "waiting_input":
        raise HTTPException(
            status_code=409, detail=f"Run is not awaiting input (status: {run.status})"
        )
    run._human_response = req.response
    run._response_ready.set()
    await asyncio.sleep(0.1)
    return _run_to_dict(run)

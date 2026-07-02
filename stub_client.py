"""Offline stub for OpenAIChatCompletionClient.

Intercepts HTTP calls at the httpx transport layer and returns deterministic,
workflow-appropriate canned responses.  No Azure account, no OpenAI API key,
and no network access are required.

Routing: the stub inspects the system-message content in the request to
identify which agent is calling, then returns a realistic canned response for
that agent's role.
"""

import json
import time
from datetime import date

import httpx
from openai import AsyncOpenAI

from agent_framework_openai import OpenAIChatCompletionClient

# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_text(content) -> str:
    """Return plain text from an OpenAI message content field (str or list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text") or item.get("content") or "")
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


def _extract_messages(raw: bytes) -> tuple[str, str]:
    """Return (system_content, last_user_content) from a raw request body."""
    try:
        payload = json.loads(raw)
        messages = payload.get("messages", [])
    except (json.JSONDecodeError, AttributeError):
        return "", ""

    system_parts: list[str] = []
    user_content = ""
    for msg in messages:
        role = msg.get("role", "")
        text = _extract_text(msg.get("content", ""))
        if role == "system":
            system_parts.append(text)
        elif role == "user":
            user_content = text  # last user message wins
    return " ".join(system_parts).lower(), user_content


# ── Per-agent canned responses ─────────────────────────────────────────────────

def _resp_drafter(user: str) -> str:
    topic = user.strip()[:80] or "the requested topic"
    return (
        f"Artificial intelligence is fundamentally reshaping how organisations approach {topic}. "
        "By automating repetitive processes and providing data-driven insights, teams can focus "
        "on higher-value creative and strategic work. The transition demands careful planning "
        "around skills development, ethical considerations, and governance frameworks."
    )


def _resp_editor(user: str) -> str:
    return (
        "Artificial intelligence is profoundly transforming how organisations operate and compete. "
        "By automating routine tasks and surfacing actionable insights from complex data, teams are "
        "freed to focus on innovation and strategic priorities—delivering faster, higher-quality "
        "outcomes. Realising this potential responsibly requires deliberate investment in upskilling, "
        "clear ethical guardrails, and a governance model that scales with adoption."
    )


_RESP_TECHNICAL = (
    "From an architecture standpoint, LLM integration introduces non-trivial latency (typically "
    "200–800 ms per call) and token costs that compound quickly at scale, making request batching "
    "and semantic caching essential. The non-deterministic nature of model outputs requires robust "
    "validation layers and graceful fallback paths in every integration point. Model versioning and "
    "regression benchmarks should be part of the CI/CD pipeline to catch capability drift early."
)

_RESP_BUSINESS = (
    "The ROI case is strongest in knowledge-intensive workflows where manual effort dominates "
    "cost—document review, support triage, and code review are showing 25–40% productivity gains "
    "in early enterprise pilots. Sustainable differentiation will come from proprietary data "
    "integrations and fine-tuned domain expertise, not from commodity model access alone. "
    "Expect a 3–6 month ramp to measurable impact; budget accordingly and set clear KPIs up front."
)

_RESP_UX = (
    "Users trust AI features most when the system is transparent about its confidence level and "
    "always provides a clear human override path—designs that omit these consistently score lower "
    "in satisfaction surveys. Conversational interfaces powered by LLMs can significantly improve "
    "accessibility for users with low digital literacy, but require careful attention to reading "
    "level and response length. Progressive disclosure—showing a summary first with a 'show "
    "reasoning' option—has proven effective at balancing informativeness with cognitive load."
)

_RESP_AGGREGATE = (
    "The team's analysis converges on a compelling but nuanced opportunity. Technically, "
    "robust API management, validation layers, and model-version governance are prerequisites "
    "for production reliability. The business case is strong—25–40% productivity gains are "
    "achievable in knowledge-intensive workflows—though durable ROI depends on proprietary "
    "data integrations rather than commodity model access. On the UX front, transparent AI "
    "with confidence indicators and clear override controls is essential to earning the user "
    "trust that drives sustained adoption. A disciplined phased rollout—governed pilot, "
    "rigorous measurement, then scaled expansion—is the path that balances ambition with risk."
)

_RESP_OPTIMIST = (
    "This is a genuinely exciting inflection point for the team. Early adopters across "
    "the industry are reporting real productivity multipliers, and the opportunity to define "
    "our own AI-native practices before they become table stakes is time-limited. If we "
    "approach this with curiosity and intention, we can build a culture of augmented creativity "
    "that becomes a lasting competitive advantage."
)

_RESP_PRAGMATIST = (
    "Before we commit resources, we need a scoped 6-week pilot with explicit success criteria "
    "and a defined rollback plan. Integration with existing CI/CD pipelines and code review "
    "workflows will require two to three sprint cycles of tooling work—that needs to be in the "
    "roadmap, not treated as a side task. We should also establish a data-handling governance "
    "policy before expanding beyond a sandboxed environment; retrofitting compliance is always "
    "more expensive than building it in."
)

_RESP_CREATIVE = (
    "What if we flipped the model entirely—instead of using AI to speed up existing work, "
    "we used it to run experiments that were previously too expensive to attempt? Imagine "
    "prototyping ten feature concepts in parallel over a single sprint, with agents building "
    "thin vertical slices and the team voting on which resonate. That kind of creative velocity "
    "is genuinely new, and the ability to fail fast cheaply is a different category of "
    "competitive advantage than incremental efficiency gains."
)


def _resp_email(user: str) -> str:
    # Try to extract the subject from the user message
    subject = "your message"
    for line in user.splitlines():
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            break
    return (
        f"Thank you for reaching out regarding {subject}. "
        "I have reviewed the details carefully and will provide my full feedback by end of week. "
        "The implications are significant enough to warrant a thorough response, and I want to "
        "ensure my input is both actionable and well-considered. "
        "Please let me know if you need anything sooner—I am happy to jump on a call."
    )


def _resp_invoice(user: str) -> str:
    # Extract vendor, amount, and date from the user message when possible
    vendor = "Acme Corp"
    amount = "1,250.00"
    inv_date = date.today().isoformat()
    due_date = date.today().replace(day=min(date.today().day + 30, 28)).isoformat()

    for line in user.splitlines():
        ll = line.lower()
        if "vendor:" in ll:
            vendor = line.split(":", 1)[1].strip()
        elif "total amount:" in ll or "amount:" in ll:
            amount = line.split(":", 1)[1].strip().lstrip("$").replace(",", "")
            try:
                amount = f"{float(amount):,.2f}"
            except ValueError:
                pass
        elif "invoice date:" in ll or "date:" in ll:
            inv_date = line.split(":", 1)[1].strip()

    return f"""INVOICE

Invoice Number : INV-{abs(hash(vendor + inv_date)) % 90000 + 10000}
Invoice Date   : {inv_date}
Payment Due    : {due_date}  (Net-30)

Bill From:
  {vendor}
  1 Vendor Plaza, Suite 100
  San Francisco, CA 94105

Bill To:
  Contoso Ltd.
  123 Enterprise Blvd
  Seattle, WA 98101

─────────────────────────────────────────────────────────
 # │ Description                          │ Qty │  Amount
─────────────────────────────────────────────────────────
 1 │ Professional Services — Q2 2026      │  1  │ ${amount}
─────────────────────────────────────────────────────────
   │ Subtotal                                   │ ${amount}
   │ Tax (0%)                                   │    $0.00
   │ TOTAL DUE                                  │ ${amount}
─────────────────────────────────────────────────────────

Payment instructions: Wire transfer or ACH to account on file.
Questions? billing@{vendor.lower().replace(" ", "")}.example.com
"""


def _resp_support(user: str) -> str:
    u = user.lower()
    if any(w in u for w in ["password", "login", "sign in", "log in", "locked out"]):
        category, complexity = "password_reset", 1
        resolution = (
            "I can help you regain access right away. Please visit our password reset page "
            "at https://app.example.com/reset and enter the email address associated with "
            "your account. You will receive a reset link within 2 minutes. If the email "
            "does not arrive, check your spam folder or reply here with your registered "
            "email and I will trigger the reset manually."
        )
    elif any(w in u for w in ["refund", "charge", "billing", "invoice", "overcharged"]):
        category, complexity = "billing_dispute", 3
        resolution = (
            "I am sorry to hear about the billing issue. I have located your account and "
            "can see the charge in question. Our billing team will review the transaction "
            "within one business day and issue a credit if the charge is confirmed as "
            "incorrect. You will receive a confirmation email once the review is complete."
        )
    elif any(w in u for w in ["cancel", "cancellation", "unsubscribe"]):
        category, complexity = "cancellation", 2
        resolution = (
            "I understand you would like to cancel your subscription. Before I process "
            "that, I want to make sure we have explored all options—many customers find "
            "that a plan adjustment or a short pause resolves their concerns. If you would "
            "still like to proceed, I can cancel effective at the end of your current "
            "billing period so you retain full access until then. Please confirm and I "
            "will action this immediately."
        )
    else:
        category, complexity = "how_to", 2
        resolution = (
            "Thank you for contacting support. Based on your description, I can help you "
            "resolve this quickly. Please follow these steps: (1) navigate to Settings > "
            "Account, (2) select the relevant option from the menu, and (3) confirm the "
            "change. If the issue persists after these steps, please reply with a "
            "screenshot and I will escalate to our technical team."
        )
    return (
        f"CATEGORY: {category}\n"
        f"COMPLEXITY: {complexity}\n"
        "RESOLUTION:\n"
        f"{resolution}"
    )


def _resp_guess(user: str) -> str:
    # The TurnManager tells the agent the exact midpoint to guess; parse it.
    import re  # noqa: PLC0415

    match = re.search(r"please guess (\d+)", user.lower())
    if match:
        return match.group(1)
    # First turn: pick the classic binary-search midpoint
    return "50"


_STUB_DEFAULT = (
    "[STUB] Offline stub response — set MOCK_MODE=false and configure "
    "Azure credentials to use the real service."
)


# ── Response routing ───────────────────────────────────────────────────────────

def _pick_response(raw: bytes) -> str:
    system, user = _extract_messages(raw)

    if "document drafter" in system:
        return _resp_drafter(user)
    if "editor" in system and ("improve" in system or "clarity" in system):
        return _resp_editor(user)
    if "technical analyst" in system:
        return _RESP_TECHNICAL
    if "business analyst" in system:
        return _RESP_BUSINESS
    if "ux analyst" in system:
        return _RESP_UX
    if "consolidate" in system and "analyst" in system:
        return _RESP_AGGREGATE
    if "optimistic team member" in system:
        return _RESP_OPTIMIST
    if "pragmatic team member" in system:
        return _RESP_PRAGMATIST
    if "creative team member" in system:
        return _RESP_CREATIVE
    if "email assistant" in system:
        return _resp_email(user)
    if "invoice processing" in system:
        return _resp_invoice(user)
    if "customer support" in system:
        return _resp_support(user)
    if "guessing game" in system or "guess" in system:
        return _resp_guess(user)
    return _STUB_DEFAULT


# ── Transport and client factory ───────────────────────────────────────────────

class _StubTransport(httpx.AsyncBaseTransport):
    """Return canned OpenAI chat-completion responses without any network access."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        ts = int(time.time())
        raw = await request.aread()
        is_stream = b'"stream":true' in raw or b'"stream": true' in raw
        text = _pick_response(raw)

        if is_stream:
            chunk_content = {
                "id": "chatcmpl-stub",
                "object": "chat.completion.chunk",
                "created": ts,
                "model": "stub",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": text},
                        "finish_reason": None,
                    }
                ],
            }
            chunk_done = {
                "id": "chatcmpl-stub",
                "object": "chat.completion.chunk",
                "created": ts,
                "model": "stub",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            body = (
                f"data: {json.dumps(chunk_content)}\n\n"
                f"data: {json.dumps(chunk_done)}\n\n"
                "data: [DONE]\n\n"
            ).encode()
            return httpx.Response(
                200,
                content=body,
                headers={"content-type": "text/event-stream"},
            )

        payload = {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": ts,
            "model": "stub",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60},
        }
        return httpx.Response(
            200,
            content=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
        )


def create_stub_client() -> OpenAIChatCompletionClient:
    """Return an OpenAIChatCompletionClient backed by the no-network stub transport."""
    async_openai = AsyncOpenAI(
        api_key="stub-key",
        http_client=httpx.AsyncClient(transport=_StubTransport()),
    )
    return OpenAIChatCompletionClient(model="stub", async_client=async_openai)

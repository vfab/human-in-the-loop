"""Tests for optional human-interaction email notifications."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import main
from workflows import WorkflowConfig
from workflows.approval_workflow import Email, send_email_via_smtp, send_notification_email


@pytest.fixture
def configured() -> WorkflowConfig:
    return WorkflowConfig(
        azure_openai_api_key="",
        azure_openai_endpoint="https://example.invalid",
        azure_openai_chat_deployment="test",
        smtp_user="sender@example.com",
        smtp_password="test-password",
        email_recipient="reviewer@example.com",
    )


def test_notification_option_is_strict_and_defaults_off() -> None:
    assert main.StartWorkflowRequest().email_notifications is False
    with pytest.raises(ValidationError):
        main.StartWorkflowRequest(email_notifications="true")


def test_start_rejects_missing_notification_configuration(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
) -> None:
    configured.smtp_password = ""
    monkeypatch.setattr(main, "_config", configured)
    monkeypatch.setattr(main, "_workflow_runners", {"approval": object()})
    monkeypatch.setattr(main, "_active_runs", {})
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.start_workflow("approval", main.StartWorkflowRequest(email_notifications=True)))
    assert exc_info.value.status_code == 503
    assert not main._active_runs


@pytest.mark.parametrize("enabled", [False, True])
def test_start_stores_notification_choice(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
    enabled: bool,
) -> None:
    monkeypatch.setattr(main, "_config", configured)
    monkeypatch.setattr(main, "_workflow_runners", {"approval": object()})
    monkeypatch.setattr(main, "_active_runs", {})
    response = asyncio.run(
        main.start_workflow("approval", main.StartWorkflowRequest(email_notifications=enabled))
    )
    assert main._active_runs[response["run_id"]]["email_notifications"] is enabled


@pytest.mark.parametrize("workflow_id", ["game", "handoff", "magentic"])
def test_unsupported_workflows_reject_email_notifications(
    monkeypatch: pytest.MonkeyPatch, configured: WorkflowConfig, workflow_id: str,
) -> None:
    monkeypatch.setattr(main, "_config", configured)
    monkeypatch.setattr(main, "_workflow_runners", {workflow_id: object()})
    monkeypatch.setattr(main, "_active_runs", {})
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.start_workflow(
            workflow_id, main.StartWorkflowRequest(input="topic", email_notifications=True)
        ))
    assert exc_info.value.status_code == 422
    assert main._active_runs == {}


def test_workflow_metadata_identifies_email_support() -> None:
    workflows = asyncio.run(main.list_workflows())
    supported = {workflow.id for workflow in workflows if workflow.email_notifications_supported}
    assert {"sequential", "concurrent", "group_chat"} <= supported
    assert not {"handoff", "magentic", "game"} & supported


@pytest.mark.parametrize("kind", ["approval", "approval_batch", "input"])
@pytest.mark.parametrize("enabled", [False, True])
def test_human_requests_notify_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
    kind: str,
    enabled: bool,
) -> None:
    sent = []

    messages = []

    def notify(config, workflow_id, request_kind, payload):
        sent.append((config, workflow_id, request_kind, payload))

    class Socket:
        async def send_json(self, message):
            messages.append(message)
            if message["type"] != "agent_message":
                main._active_runs["run"]["waiters"]["request"].set_result({"response": "ok"})

        async def receive(self):
            await asyncio.Event().wait()

    monkeypatch.setattr(main, "_config", configured)
    monkeypatch.setattr(main, "send_notification_email", notify)
    monkeypatch.setattr(main, "_active_runs", {
        "run": {
            "workflow_id": "game",
            "email_notifications": enabled,
            "pending_requests": {},
            "waiters": {},
        }
    })
    result = asyncio.run(main._request_response(
        Socket(), "run", "request", kind, {"type": kind, "items": []}
    ))
    assert result == {"response": "ok"}
    payload = {"type": kind, "items": []}
    assert sent == ([(configured, "game", kind, payload)] if enabled else [])
    assert messages[-1].get("email_notification") == ("sent" if enabled else None)
    assert main._active_runs["run"]["pending_requests"] == {}


def test_notification_failure_is_visible_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    messages = []

    def fail(*_args):
        raise OSError("sensitive SMTP details")

    class Socket:
        async def send_json(self, message):
            messages.append(message)
            if message["type"] == "input_required":
                main._active_runs["run"]["waiters"]["request"].set_result({"input": "answer"})

        async def receive(self):
            await asyncio.Event().wait()

    monkeypatch.setattr(main, "_config", configured)
    monkeypatch.setattr(main, "send_notification_email", fail)
    monkeypatch.setattr(main, "_active_runs", {
        "run": {"workflow_id": "game", "email_notifications": True, "pending_requests": {}, "waiters": {}}
    })
    result = asyncio.run(main._request_response(
        Socket(), "run", "request", "input", {"type": "input_required"}
    ))
    assert result == {"input": "answer"}
    assert any("Email notification failed" in message.get("content", "") for message in messages)
    assert messages[-1]["email_notification"] == "failed"
    assert "sensitive SMTP details" not in str(messages)
    assert "sensitive SMTP details" not in caplog.text


def test_notification_email_sends_generic_message(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
) -> None:
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def login(self, user, password):
            pass

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr("workflows.approval_workflow.smtplib.SMTP_SSL", FakeSMTP)
    send_notification_email(configured, "game", "input", {})
    assert len(sent) == 1
    assert sent[0]["To"] == "reviewer@example.com"
    assert "game" in sent[0].get_content()
    assert "five minutes" in sent[0].get_content()

    send_email_via_smtp(
        configured, Email("team@example.com", "author@example.com", "Test", "Incoming"), "Draft"
    )
    assert sent[1]["Subject"] == "Re: Test"
    assert sent[1]["To"] == "reviewer@example.com"
    assert sent[1].get_content().strip() == "Draft"


def test_concurrent_batch_notification_contains_each_analyst_response(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
) -> None:
    sent = []
    monkeypatch.setattr(
        "workflows.approval_workflow.send_smtp_message",
        lambda _config, subject, body: sent.append((subject, body)),
    )
    payload = {
        "items": [
            {"label": "Technical Analyst", "content": "Technical assessment"},
            {"label": "Business Analyst", "content": "Business assessment"},
            {"label": "UX Analyst", "content": "UX assessment"},
        ]
    }

    send_notification_email(configured, "concurrent", "approval_batch", payload)
    assert len(sent) == 1
    subject, body = sent[0]
    assert "review" in subject.lower()
    for item in payload["items"]:
        assert item["label"] in body
        assert item["content"] in body
    assert "dashboard" in body
    assert "five minutes" in body


@pytest.mark.parametrize(
    ("workflow_id", "kind", "payload", "expected"),
    [
        ("approval", "approval", {"prompt": "Send the draft?", "content": "Draft response"}, ["Send the draft?", "Draft response"]),
        ("concurrent", "approval", {"prompt": "Accept the summary?", "content": "Synthesized summary"}, ["Accept the summary?", "Synthesized summary"]),
        ("group_chat", "approval", {"prompt": "Accept the discussion?", "content": "Discussion summary"}, ["Accept the discussion?", "Discussion summary"]),
        ("group_chat", "input", {"prompt": "Give guidance", "content": "Pragmatist response"}, ["Give guidance", "Pragmatist response"]),
        ("sequential", "input", {"prompt": "Give feedback", "content": "Editor response"}, ["Give feedback", "Editor response"]),
        ("game", "input", {"prompt": "Guess: 5", "options": ["higher", "lower", "correct", "exit"]}, ["Guess: 5", "higher", "lower", "correct", "exit"]),
    ],
)
def test_notification_contains_review_context(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
    workflow_id: str,
    kind: str,
    payload: dict,
    expected: list[str],
) -> None:
    sent = []
    monkeypatch.setattr(
        "workflows.approval_workflow.send_smtp_message",
        lambda _config, _subject, body: sent.append(body),
    )
    send_notification_email(configured, workflow_id, kind, payload)
    for text in expected:
        assert text in sent[0]
    assert "dashboard" in sent[0]


@pytest.mark.parametrize("workflow_id", ["group_chat", "sequential"])
def test_steering_request_contains_the_response_for_review(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
    workflow_id: str,
) -> None:
    if workflow_id == "group_chat":
        from workflows import group_chat_workflow as module
        runner = module.run_group_chat_workflow
        agent = "pragmatist"
    else:
        from workflows import sequential_workflow as module
        runner = module.run_sequential_workflow
        agent = "editor"

    class Event:
        def __init__(self, type, data, source_executor_id="system", request_id="request"):
            self.type = type
            self.data = data
            self.source_executor_id = source_executor_id
            self.request_id = request_id

    class Response:
        agent_response = SimpleNamespace(text="Response to review")
        full_conversation = [
            SimpleNamespace(role="user", author_name=None, text="Original topic"),
            SimpleNamespace(role="assistant", author_name="first_agent", text="First agent response"),
            SimpleNamespace(role="assistant", author_name=agent, text="Response to review"),
        ]

    class Builder:
        def __init__(self, **_kwargs):
            pass

        def with_request_info(self, **_kwargs):
            return self

        def build(self):
            return self

        async def run(self, *_args, **_kwargs):
            yield Event("request_info", Response(), agent)

    class Client:
        def as_agent(self, **_kwargs):
            return object()

    configured.azure_openai_api_key = "test-key"
    monkeypatch.setattr(module, "WorkflowEvent", Event)
    monkeypatch.setattr(module, "AgentExecutorResponse", Response)
    monkeypatch.setattr(module, "SequentialBuilder", Builder)
    monkeypatch.setattr(module, "OpenAIChatCompletionClient", lambda **_kwargs: Client())

    async def get_request():
        stream = runner(configured, "topic")
        try:
            while True:
                event = await anext(stream)
                if event.type == "input_required":
                    return event
        finally:
            await stream.aclose()

    data = asyncio.run(get_request()).data
    assert data["content"] == "Response to review"
    assert "Original topic" in data["email_context"]
    assert "first_agent" in data["email_context"]
    assert "First agent response" in data["email_context"]


@pytest.mark.parametrize("event_type", ["approval_required", "approval_batch", "input_required"])
def test_dashboard_passes_request_context_to_notification(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
    event_type: str,
) -> None:
    captured = []

    async def runner(*_args):
        yield {
            "type": event_type,
            "data": {
                "request_id": "request",
                "prompt": "Review",
                "content": "Context for review",
                "email_context": "Prior context",
                "items": [{"request_id": "item", "content": "Batch item"}],
            },
        }

    async def request_response(_socket, _run_id, _request_id, _kind, payload):
        captured.append(payload)
        return {"approved": False, "input": ""}

    class Socket:
        async def accept(self):
            pass

        async def send_json(self, _message):
            pass

    monkeypatch.setattr(main, "_config", configured)
    monkeypatch.setattr(main, "_workflow_runners", {"game": runner})
    monkeypatch.setattr(main, "_request_response", request_response)
    monkeypatch.setattr(main, "_active_runs", {
        "run": {"workflow_id": "game", "input": "", "pending_requests": {}, "waiters": {}}
    })
    asyncio.run(main.websocket_workflow_stream(Socket(), "game", "run"))
    assert captured[0]["prompt"] == "Review"
    if event_type == "approval_batch":
        assert captured[0]["items"][0]["content"] == "Batch item"
    else:
        assert captured[0]["content"] == "Context for review"
    assert captured[0]["email_context"] == "Prior context"


@pytest.mark.parametrize(
    ("workflow_id", "kind", "payload", "expected"),
    [
        ("approval", "approval", {"prompt": "Send?", "content": "Draft response", "email_context": "Original email:\nFrom: sender\nSubject: Question\n\nOriginal request"}, ["Original request", "Subject: Question", "Draft response"]),
        ("sequential", "input", {"prompt": "Feedback?", "content": "Editor response", "email_context": "Topic: Example\nDrafter:\nOriginal draft"}, ["Topic: Example", "Original draft", "Editor response"]),
        ("group_chat", "input", {"prompt": "Guidance?", "content": "Pragmatist response", "email_context": "Topic: Example\nOptimist:\nEarlier response"}, ["Topic: Example", "Earlier response", "Pragmatist response"]),
        ("group_chat", "approval", {"prompt": "Accept?", "content": "Optimist: A\nPragmatist: B\nCreative: C", "email_context": "Topic: Example"}, ["Topic: Example", "Optimist: A", "Pragmatist: B", "Creative: C"]),
        ("game", "input", {"prompt": "Guess: 5", "options": ["higher", "lower"], "email_context": "Think of a number between 1 and 20."}, ["between 1 and 20", "Guess: 5", "higher", "lower"]),
        ("concurrent", "approval", {"prompt": "Accept summary?", "content": "Summary", "email_context": "Topic: Example\nTechnical Analyst: Analysis"}, ["Topic: Example", "Technical Analyst: Analysis", "Summary"]),
    ],
)
def test_notification_contains_complete_context(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
    workflow_id: str,
    kind: str,
    payload: dict,
    expected: list[str],
) -> None:
    messages = []
    monkeypatch.setattr(
        "workflows.approval_workflow.send_smtp_message",
        lambda _config, _subject, body: messages.append(body),
    )
    send_notification_email(configured, workflow_id, kind, payload)
    for text in expected:
        assert text in messages[0]


def test_approval_workflow_provides_original_email_for_review(
    monkeypatch: pytest.MonkeyPatch, configured: WorkflowConfig,
) -> None:
    from workflows import approval_workflow as module

    class Agent:
        async def run(self, _message):
            return SimpleNamespace(text="Draft reply")

    class Client:
        def as_agent(self, **_kwargs):
            return Agent()

    configured.azure_openai_api_key = "test-key"
    monkeypatch.setattr(module, "OpenAIChatCompletionClient", lambda **_kwargs: Client())

    async def get_request():
        stream = module.run_approval_workflow(configured, "status_update")
        try:
            while True:
                event = await anext(stream)
                if event.type == "approval_required":
                    return event.data
        finally:
            await stream.aclose()

    data = asyncio.run(get_request())
    email = module.EMAIL_SCENARIOS["status_update"][0]
    assert email.body in data["email_context"]
    assert email.sender in data["email_context"]
    assert email.subject in data["email_context"]
    assert data["content"] == "Draft reply"


def test_review_conversation_uses_public_messages_and_excludes_system_instructions() -> None:
    from agent_framework import Message
    from workflows import format_review_conversation

    conversation = [
        Message("system", ["Internal instructions"]),
        Message("user", ["Document topic"]),
        Message("assistant", ["First draft"], author_name="drafter"),
        Message("assistant", ["Editor review"], author_name="editor"),
    ]
    result = format_review_conversation(conversation)
    assert "Document topic" in result
    assert "drafter:\nFirst draft" in result
    assert "editor:\nEditor review" in result
    assert "Internal instructions" not in result


def test_game_request_includes_actual_number_range(
    monkeypatch: pytest.MonkeyPatch, configured: WorkflowConfig,
) -> None:
    from workflows import game_workflow as module

    class Event:
        def __init__(self, type, data, source_executor_id="system", request_id="request"):
            self.type = type
            self.data = data
            self.request_id = request_id

    class Builder:
        def __init__(self, **_kwargs):
            pass

        def add_edge(self, *_args):
            return self

        def build(self):
            return self

        async def run(self, *_args, **_kwargs):
            yield Event("request_info", module.HumanFeedbackRequest("The agent guessed: 12"))

    class Client:
        def as_agent(self, **_kwargs):
            return object()

    configured.azure_openai_api_key = "test-key"
    monkeypatch.setattr(module, "WorkflowEvent", Event)
    monkeypatch.setattr(module, "WorkflowBuilder", Builder)
    monkeypatch.setattr(module, "TurnManager", lambda **_kwargs: object())
    monkeypatch.setattr(module, "OpenAIChatCompletionClient", lambda **_kwargs: Client())

    async def get_request():
        stream = module.run_game_workflow(configured, "50")
        try:
            while True:
                event = await anext(stream)
                if event.type == "input_required":
                    return event.data
        finally:
            await stream.aclose()

    data = asyncio.run(get_request())
    assert "between 1 and 50" in data["email_context"]
    assert "12" in data["prompt"]
    assert data["options"] == ["higher", "lower", "correct", "exit"]


def test_concurrent_summary_includes_approved_analyst_context(
    monkeypatch: pytest.MonkeyPatch, configured: WorkflowConfig,
) -> None:
    from workflows import concurrent_workflow as module

    class Event:
        def __init__(self, type, data, source_executor_id="system", request_id="request"):
            self.type = type
            self.data = data
            self.source_executor_id = source_executor_id
            self.request_id = request_id

    class Response:
        def __init__(self, text):
            self.agent_response = SimpleNamespace(text=text)

    class Builder:
        def __init__(self, **_kwargs):
            pass

        def with_aggregator(self, _aggregator):
            return self

        def with_request_info(self, **_kwargs):
            return self

        def build(self):
            return self

        async def run(self, *_args, **kwargs):
            if "responses" in kwargs:
                yield Event("output", "Synthesized summary")
            else:
                yield Event("request_info", Response("Technical analysis"), "technical_analyst", "a")
                yield Event("request_info", Response("Business analysis"), "business_analyst", "b")
                yield Event("request_info", Response("UX analysis"), "ux_analyst", "c")

    class Client:
        def as_agent(self, **_kwargs):
            return object()

    class Approval:
        @classmethod
        def approve(cls):
            return cls()

    configured.azure_openai_api_key = "test-key"
    monkeypatch.setattr(module, "WorkflowEvent", Event)
    monkeypatch.setattr(module, "AgentExecutorResponse", Response)
    monkeypatch.setattr(module, "AgentRequestInfoResponse", Approval)
    monkeypatch.setattr(module, "ConcurrentBuilder", Builder)
    monkeypatch.setattr(module, "OpenAIChatCompletionClient", lambda **_kwargs: Client())

    async def get_requests():
        stream = module.run_concurrent_workflow(configured, "Analysis topic")
        try:
            while True:
                event = await anext(stream)
                if event.type == "approval_batch":
                    batch = event.data
                    event = await stream.asend({"decisions": {"a": True, "b": True, "c": True}})
                    while event.type != "approval_required":
                        event = await anext(stream)
                    return batch, event.data
        finally:
            await stream.aclose()

    batch, summary = asyncio.run(get_requests())
    assert "Analysis topic" in batch["email_context"]
    assert [item["content"] for item in batch["items"]] == [
        "Technical analysis", "Business analysis", "UX analysis"
    ]
    for text in ("Analysis topic", "Technical analysis", "Business analysis", "UX analysis"):
        assert text in summary["email_context"]
    assert summary["content"] == "Synthesized summary"


@pytest.mark.parametrize(
    ("workflow_id", "request_type"),
    [("sequential", "input_required"), ("concurrent", "approval_batch"), ("group_chat", "input_required")],
)
def test_notification_contains_workflow_output_at_each_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    configured: WorkflowConfig,
    workflow_id: str,
    request_type: str,
) -> None:
    emails = []
    emitted = []

    async def runner(*_args):
        yield {"type": "agent_message", "data": {"agent": "first", "content": "First output"}}
        yield {"type": "agent_message", "data": {"agent": "second", "content": "Second output\nwith details"}}
        yield {
            "type": request_type,
            "data": {"request_id": "first-review", "prompt": "Review", "items": []},
        }
        yield {"type": "agent_message", "data": {"agent": "first", "content": "Revised output"}}
        yield {
            "type": request_type,
            "data": {"request_id": "second-review", "prompt": "Review again", "items": []},
        }

    def send(_config, _subject, body):
        emails.append(body)

    class Socket:
        async def accept(self):
            pass

        async def receive(self):
            await asyncio.Event().wait()

        async def send_json(self, message):
            emitted.append(message)
            if message["type"] == request_type:
                main._active_runs["run"]["waiters"][message["request_id"]].set_result(
                    {"type": "input", "input": "feedback", "decisions": {}}
                )

    monkeypatch.setattr("workflows.approval_workflow.send_smtp_message", send)
    monkeypatch.setattr(main, "_config", configured)
    monkeypatch.setattr(main, "_workflow_runners", {workflow_id: runner})
    monkeypatch.setattr(main, "_active_runs", {
        "run": {
            "workflow_id": workflow_id, "input": "Example topic",
            "email_notifications": True, "pending_requests": {}, "waiters": {},
        }
    })
    asyncio.run(main.websocket_workflow_stream(Socket(), workflow_id, "run"))
    assert len(emails) == 2
    for email in emails:
        assert "Workflow output" in email
        assert "first:\nFirst output" in email
        assert "second:\nSecond output\nwith details" in email
        assert email.index("first:\nFirst output") < email.index("second:\nSecond output")
    assert "Revised output" not in emails[0]
    assert "first:\nRevised output" in emails[1]
    assert emails[1].index("second:\nSecond output") < emails[1].index("first:\nRevised output")
    assert "workflow_output" not in main._active_runs["run"]


def test_notification_output_is_isolated_between_concurrent_runs(
    monkeypatch: pytest.MonkeyPatch, configured: WorkflowConfig,
) -> None:
    emails = []

    async def runner(_config, topic):
        yield {"type": "agent_message", "data": {"agent": "analyst", "content": topic}}
        await asyncio.sleep(0)
        yield {"type": "input_required", "data": {"request_id": "review", "prompt": topic}}

    class Socket:
        def __init__(self, run_id):
            self.run_id = run_id

        async def accept(self):
            pass

        async def receive(self):
            await asyncio.Event().wait()

        async def send_json(self, message):
            if message["type"] == "input_required":
                main._active_runs[self.run_id]["waiters"]["review"].set_result({"input": ""})

    monkeypatch.setattr(
        "workflows.approval_workflow.send_smtp_message",
        lambda _config, _subject, body: emails.append(body),
    )
    monkeypatch.setattr(main, "_config", configured)
    monkeypatch.setattr(main, "_workflow_runners", {"sequential": runner})
    monkeypatch.setattr(main, "_active_runs", {
        run_id: {
            "workflow_id": "sequential", "input": topic, "email_notifications": True,
            "pending_requests": {}, "waiters": {},
        }
        for run_id, topic in [("run-a", "Private output A"), ("run-b", "Private output B")]
    })

    async def run_both():
        await asyncio.gather(
            main.websocket_workflow_stream(Socket("run-a"), "sequential", "run-a"),
            main.websocket_workflow_stream(Socket("run-b"), "sequential", "run-b"),
        )

    asyncio.run(run_both())
    assert len(emails) == 2
    for own, other in [("Private output A", "Private output B"), ("Private output B", "Private output A")]:
        email = next(body for body in emails if f"Request:\n{own}" in body)
        assert f"analyst:\n{own}" in email
        assert other not in email

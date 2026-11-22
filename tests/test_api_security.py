"""Tests for API validation, approval handling, and safe client errors."""

import asyncio
import logging

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

import main
from main import ApprovalRequest, InputRequest, StartWorkflowRequest
from workflows.concurrent_workflow import _is_batch_item_approved


class RecordingWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def accept(self) -> None:
        pass

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)

    async def close(self) -> None:
        pass


def test_start_request_rejects_non_string_and_oversized_input() -> None:
    with pytest.raises(ValidationError):
        StartWorkflowRequest.model_validate({"input": 42})

    with pytest.raises(ValidationError):
        StartWorkflowRequest.model_validate({"input": "x" * 10_001})


def test_approval_request_rejects_non_boolean_decisions_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ApprovalRequest.model_validate({
            "run_id": "run",
            "request_id": "request",
            "decisions": {"item": "yes"},
        })

    with pytest.raises(ValidationError):
        InputRequest.model_validate({
            "run_id": "run",
            "request_id": "request",
            "input": "answer",
            "unexpected": True,
        })


def test_validation_error_response_does_not_echo_user_input() -> None:
    secret_input = "validation-error-sensitive-input"
    try:
        StartWorkflowRequest.model_validate({"input": secret_input, "unexpected": True})
    except ValidationError as exc:
        validation_error = exc
    else:
        pytest.fail("Expected request validation to fail")

    from fastapi.exceptions import RequestValidationError

    response = asyncio.run(
        main.request_validation_exception_handler(
            Request(scope={"type": "http"}),
            RequestValidationError(validation_error.errors()),
        )
    )

    assert response.status_code == 422
    assert secret_input.encode() not in response.body


def test_approval_rejects_a_run_from_another_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "_active_runs",
        {
            "run": {
                "workflow_id": "concurrent",
                "pending_requests": {},
                "waiters": {},
            }
        },
    )
    request = ApprovalRequest(run_id="run", request_id="request", approved=True)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.submit_approval("sequential", request))

    assert exc_info.value.status_code == 404


def test_approval_rejects_request_ids_that_are_not_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "_active_runs",
        {
            "run": {
                "workflow_id": "concurrent",
                "pending_requests": {},
                "waiters": {},
            }
        },
    )
    request = ApprovalRequest(run_id="run", request_id="unknown", approved=True)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.submit_approval("concurrent", request))

    assert exc_info.value.status_code == 409


def test_approval_delivers_response_to_matching_pending_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def submit_approval() -> None:
        waiter = asyncio.get_running_loop().create_future()
        monkeypatch.setattr(
            main,
            "_active_runs",
            {
                "run": {
                    "workflow_id": "approval",
                    "pending_requests": {
                        "approval-request": {
                            "kind": "approval",
                            "decision_ids": set(),
                        }
                    },
                    "waiters": {"approval-request": waiter},
                }
            },
        )

        result = await main.submit_approval(
            "approval",
            ApprovalRequest(
                run_id="run",
                request_id="approval-request",
                approved=True,
                feedback="Reviewed",
            ),
        )

        assert result == {"status": "accepted"}
        assert waiter.result() == {
            "type": "approval",
            "approved": True,
            "feedback": "Reviewed",
            "decisions": {},
        }

    asyncio.run(submit_approval())


def test_batch_approval_requires_decisions_for_exact_pending_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def submit_partial_decision() -> None:
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(
            main,
            "_active_runs",
            {
                "run": {
                    "workflow_id": "concurrent",
                    "pending_requests": {
                        "batch": {
                            "kind": "approval_batch",
                            "decision_ids": {"item-a", "item-b"},
                        }
                    },
                    "waiters": {"batch": loop.create_future()},
                }
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            await main.submit_approval(
                "concurrent",
                ApprovalRequest(
                    run_id="run",
                    request_id="batch",
                    approved=True,
                    decisions={"item-a": True},
                ),
            )

        assert exc_info.value.status_code == 422

    asyncio.run(submit_partial_decision())


def test_batch_approval_delivers_explicit_decisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def submit_complete_decisions() -> None:
        waiter = asyncio.get_running_loop().create_future()
        monkeypatch.setattr(
            main,
            "_active_runs",
            {
                "run": {
                    "workflow_id": "concurrent",
                    "pending_requests": {
                        "batch": {
                            "kind": "approval_batch",
                            "decision_ids": {"item-a", "item-b"},
                        }
                    },
                    "waiters": {"batch": waiter},
                }
            },
        )

        await main.submit_approval(
            "concurrent",
            ApprovalRequest(
                run_id="run",
                request_id="batch",
                approved=False,
                decisions={"item-a": True, "item-b": False},
            ),
        )

        assert waiter.result()["decisions"] == {"item-a": True, "item-b": False}

    asyncio.run(submit_complete_decisions())


def test_input_response_requires_a_matching_pending_input_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def submit_input() -> None:
        waiter = asyncio.get_running_loop().create_future()
        monkeypatch.setattr(
            main,
            "_active_runs",
            {
                "run": {
                    "workflow_id": "sequential",
                    "pending_requests": {
                        "input-request": {
                            "kind": "input",
                            "decision_ids": set(),
                        }
                    },
                    "waiters": {"input-request": waiter},
                }
            },
        )

        await main.submit_input(
            "sequential",
            InputRequest(
                run_id="run",
                request_id="input-request",
                input="new direction",
            ),
        )

        assert waiter.result() == {"type": "input", "input": "new direction"}

    asyncio.run(submit_input())


def test_error_events_and_input_are_not_exposed_to_websocket_or_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user_input = "private-user-input-sentinel"
    internal_error = "internal-error-sensitive-detail"

    async def failing_workflow(*_args):
        raise RuntimeError(internal_error)
        yield  # Make this an async generator.

    monkeypatch.setattr(main, "_workflow_runners", {"game": failing_workflow})
    monkeypatch.setattr(
        main,
        "_active_runs",
        {
            "run": {
                "workflow_id": "game",
                "input": user_input,
                "pending_requests": {},
                "waiters": {},
            }
        },
    )
    websocket = RecordingWebSocket()

    with caplog.at_level(logging.ERROR, logger="main"):
        asyncio.run(main.websocket_workflow_stream(websocket, "game", "run"))

    assert not any(user_input in record.getMessage() for record in caplog.records)
    assert not any(internal_error in record.getMessage() for record in caplog.records)
    errors = [message for message in websocket.messages if message.get("type") == "error"]
    assert errors
    assert all(internal_error not in message.get("content", "") for message in errors)
    assert all("Workflow failed" in message.get("content", "") for message in errors)


def test_email_api_returns_generic_error_without_logging_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import agent_framework_openai

    class StubChatClient:
        def as_agent(self, **_kwargs):
            return object()

    monkeypatch.setattr(
        agent_framework_openai,
        "OpenAIChatClient",
        lambda: StubChatClient(),
    )
    import app_server

    secret_error = "email-provider-error-sensitive-detail"

    async def fail_processing(_email) -> str:
        raise RuntimeError(secret_error)

    monkeypatch.setattr(app_server.assistant, "process_email", fail_processing)

    with caplog.at_level(logging.ERROR, logger="app_server"):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(app_server.run_workflow())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Email processing failed."
    assert secret_error not in caplog.text


def test_workflow_error_event_does_not_expose_exception_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_error = "workflow-event-sensitive-detail"

    async def failing_workflow(*_args):
        yield {"type": "error", "data": {"message": secret_error}}

    monkeypatch.setattr(main, "_workflow_runners", {"game": failing_workflow})
    monkeypatch.setattr(
        main,
        "_active_runs",
        {
            "run": {
                "workflow_id": "game",
                "input": "",
                "pending_requests": {},
                "waiters": {},
            }
        },
    )
    websocket = RecordingWebSocket()

    asyncio.run(main.websocket_workflow_stream(websocket, "game", "run"))

    errors = [message for message in websocket.messages if message.get("type") == "error"]
    assert len(errors) == 1
    assert errors[0]["content"] == "Workflow failed. Check server logs."
    assert secret_error not in str(websocket.messages)


def test_safe_configuration_error_remains_actionable_to_dashboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def workflow_with_missing_config(*_args):
        yield {
            "type": "error",
            "data": {"message": "Missing AZURE_OPENAI_ENDPOINT"},
        }

    monkeypatch.setattr(
        main,
        "_workflow_runners",
        {"game": workflow_with_missing_config},
    )
    monkeypatch.setattr(
        main,
        "_active_runs",
        {
            "run": {
                "workflow_id": "game",
                "input": "",
                "pending_requests": {},
                "waiters": {},
            }
        },
    )
    websocket = RecordingWebSocket()

    asyncio.run(main.websocket_workflow_stream(websocket, "game", "run"))

    errors = [message for message in websocket.messages if message.get("type") == "error"]
    assert errors[0]["content"] == "Missing AZURE_OPENAI_ENDPOINT"


def test_input_response_rejects_run_from_another_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "_active_runs",
        {
            "run": {
                "workflow_id": "concurrent",
                "pending_requests": {},
                "waiters": {},
            }
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            main.submit_input(
                "sequential",
                InputRequest(run_id="run", request_id="request", input="answer"),
            )
        )

    assert exc_info.value.status_code == 404


def test_missing_batch_decision_is_not_approval() -> None:
    assert _is_batch_item_approved({}, "unreviewed-item") is False
    assert _is_batch_item_approved({"reviewed-item": True}, "reviewed-item") is True
    assert _is_batch_item_approved({"reviewed-item": False}, "reviewed-item") is False

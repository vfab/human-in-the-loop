"""Regression tests for dashboard startup configuration warnings."""

import asyncio
import logging

import pytest

import main
from workflows import WorkflowConfig


@pytest.mark.parametrize(
    ("api_key", "endpoint", "deployment", "expected_error"),
    [
        ("", "https://example.openai.azure.com/", "gpt-4o", None),
        ("test-api-key", "https://example.openai.azure.com/", "gpt-4o", None),
        ("", "", "gpt-4o", "Missing AZURE_OPENAI_ENDPOINT"),
        ("test-api-key", "", "gpt-4o", "Missing AZURE_OPENAI_ENDPOINT"),
        (
            "",
            "https://example.openai.azure.com/",
            "",
            "Missing AZURE_OPENAI_CHAT_DEPLOYMENT_NAME or AZURE_OPENAI_CHAT_MODEL",
        ),
        (
            "test-api-key",
            "https://example.openai.azure.com/",
            "",
            "Missing AZURE_OPENAI_CHAT_DEPLOYMENT_NAME or AZURE_OPENAI_CHAT_MODEL",
        ),
    ],
)
def test_startup_configuration_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    api_key: str,
    endpoint: str,
    deployment: str,
    expected_error: str | None,
) -> None:
    config = WorkflowConfig(
        azure_openai_api_key=api_key,
        azure_openai_endpoint=endpoint,
        azure_openai_chat_deployment=deployment,
    )
    monkeypatch.setattr(WorkflowConfig, "from_env", lambda: config)
    monkeypatch.setattr(main, "_config", None)
    monkeypatch.setattr(main, "_workflow_runners", {})
    monkeypatch.setattr(main, "_active_runs", {})

    async def run_startup() -> None:
        async with main.lifespan(main.app):
            assert main._config is config
            assert len(main._workflow_runners) == 7

    with caplog.at_level(logging.WARNING, logger="main"):
        asyncio.run(run_startup())

    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == "main" and record.levelno == logging.WARNING
    ]
    if expected_error is None:
        assert warnings == []
    else:
        assert warnings == [
            f"Missing Azure OpenAI configuration. {expected_error}. "
            "Please set the required values in .env"
        ]
    assert "test-api-key" not in caplog.text

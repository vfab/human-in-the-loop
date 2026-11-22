# Repository Coding Standards

These standards apply to changes across this repository. Follow project conventions and the documentation in [README.md](../README.md) and [LOCAL_DEVELOPMENT.md](../LOCAL_DEVELOPMENT.md).

## Code quality

- Write clear, maintainable Python using four-space indentation, descriptive names, and type annotations for public functions and nontrivial interfaces.
- Keep HTTP handling and request/response validation at the FastAPI boundary. Keep workflow orchestration in `workflows/` and reuse project configuration and workflow abstractions.
- Define explicit Pydantic request models for FastAPI endpoints. Validate types, required fields, and reasonable input size limits before accepting requests; do not use unconstrained `dict[str, Any]` payloads for API contracts.
- Prefer small, single-purpose functions and classes. Handle expected failures explicitly; do not swallow exceptions or return success-shaped fallback values.
- Use supported public APIs from dependencies. Do not import private or underscored SDK internals unless a reviewed compatibility exception is documented.
- Keep changes focused. Update or add tests for behavior changes, using the project pytest suite and conventions.
- Do not add a new framework, formatter, linter, or test runner without approval.

## Project patterns

- Load service configuration through `WorkflowConfig.from_env()` and validate required settings before starting a workflow. Use the configured Azure identity fallback instead of introducing another credential path.
- Use the FastAPI lifespan for application startup and shutdown setup.
- Implement dashboard workflows as async generators yielding `WorkflowEvent` values. Keep request handling in the API layer and preserve the human-response protocol.
- Keep synchronous I/O, such as SMTP calls, off the async event loop with `asyncio.to_thread()`.
- Test configuration and logging behavior with pytest fixtures such as `monkeypatch` and `caplog`; assert that secrets are not present in logs.

## Approved libraries and tools

The approved direct Python runtime dependencies are declared in [requirements.txt](../requirements.txt):

- `agent-framework-openai` and `agent-framework-orchestrations` for the Microsoft Agent Framework integrations used by this project.
- `azure-identity` for Azure authentication.
- `fastapi` and `uvicorn[standard]` for the HTTP API and ASGI server.
- `python-dotenv` for loading local development configuration.
- Python standard library modules.

Use the repository's documented Python environment and toolchain. Azure CLI, Docker Desktop, and Terraform are used only for the documented Azure and container workflows.

- Do not add or use an unapproved third-party package or developer tool. Get explicit human approval before introducing one, and update the applicable dependency manifest and documentation.
- Prefer an approved dependency or project helper over adding another package.
- Do not install packages from arbitrary URLs, untrusted indexes, or source archives.

## Security requirements

- Never hardcode secrets, credentials, API keys, access tokens, or secret connection strings in source code, tests, configuration, logs, or documentation. Read secrets from approved runtime configuration; keep local secret files out of version control.
- Never bypass input validation. Validate untrusted data at API and other trust boundaries with project validation mechanisms before using it in workflow execution, prompts, storage, or external calls.
- Never pass raw untrusted input into prompts as instructions. Keep trusted instructions separate from user content, and preserve human approval gates for actions that require them.
- Human approval must fail closed: a timeout, missing decision, or malformed reply is not approval for a consequential action.
- Do not log secrets, authentication material, or full user-supplied content. Return actionable errors without exposing credentials, internal stack traces, or sensitive configuration.
- Send generic, non-sensitive error messages to API and WebSocket clients; retain diagnostic details only in appropriately protected server logs.
- Use approved identity mechanisms and least-privilege access for Azure resources. Never embed credentials in code or automate access beyond the user's authorization.

## Changes to dependencies and external services

- Keep changes compatible with the supported project setup documented in the README and development guides.
- Add tests that cover validation, error paths, and changed workflow behavior. Unit tests must not make unintended calls to live Azure services, model endpoints, or email systems.
- Do not change deployment targets, grant access, or perform a deployment as an incidental part of a code change. Follow the repository's documented deployment process and obtain explicit authorization for consequential operations.

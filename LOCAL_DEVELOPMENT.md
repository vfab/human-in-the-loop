---
title: Local Development Guide
description: Set up, configure, run, and troubleshoot the HITL dashboard locally
---

## Quick Start

1. Create a virtual environment and install the project dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set the Azure OpenAI endpoint and deployment
   name. For Azure CLI authentication, run `az login`. See
   [Configuration](#configuration) for the supported variables.
3. In VS Code, select **HITL Dashboard** in **Run and Debug** and press **F5**
   to debug or **Ctrl+F5** to run without debugging.
4. Open <http://127.0.0.1:8000/>. Press **Shift+F5** to stop the server.

The VS Code launch configuration uses `.venv\Scripts\python.exe`, starts Uvicorn
with reload enabled, and opens the integrated browser after the server is ready.
The Microsoft Python and Python Debugger extensions are required.

To run without VS Code:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## Configuration

Use `.env.example` as the template for a root-level `.env` file. The application
requires `AZURE_OPENAI_ENDPOINT` and either `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`
or `AZURE_OPENAI_CHAT_MODEL`.

* `AZURE_OPENAI_API_KEY`: optional for local use; if omitted, workflows use
  `AzureCliCredential` and require `az login`
* `AZURE_OPENAI_API_VERSION`: optional; the application default is
  `2024-10-21`
* `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `EMAIL_RECIPIENT`:
  optional email workflow settings; the default SMTP port is `465`

The `.env.example` file may explicitly set an API version; that value overrides
the application default. Keep `.env` out of source control and never commit
credentials. Container authentication and the current managed-identity
limitation are documented in [CONTAINER_AUTH.md](CONTAINER_AUTH.md).

## Run and Test Workflows

The dashboard provides these workflows:

| Workflow ID | Purpose |
| --- | --- |
| `concurrent` | Analyze a topic from multiple perspectives |
| `group_chat` | Facilitate a team discussion |
| `sequential` | Review a document through a sequence of agents |
| `approval` | Demonstrate an approval-enabled email workflow |
| `game` | Play an interactive guessing game |
| `handoff` | Route a support conversation between agents |
| `magentic` | Coordinate specialist agents on an analysis task |

The dashboard API includes `GET /workflows`, `GET /health`, and `GET /docs`.
Workflow updates are streamed over WebSockets.

Run the test suite from the activated project environment:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The test suite requires `pytest` and `pytest-asyncio`, which are not included in
the runtime dependencies in `requirements.txt`. Install them in the virtual
environment if needed.

Compile the top-level Python modules if you only need a syntax check:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py app_server.py diagnostic.py
```

## Troubleshooting

### A Python dependency is missing

Confirm VS Code selected the project virtual environment, then install
dependencies with `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.

### Port 8000 is already in use

Stop the other server or change the port in `.vscode/launch.json`.

### Workflow execution fails

Check `AZURE_OPENAI_ENDPOINT` and the deployment name in `.env`. For Azure CLI
authentication, run `az login` and confirm the signed-in identity can access
the Azure OpenAI resource. Inspect the integrated terminal for the application
error.

### WebSocket connection fails

Confirm the server is running and open <http://127.0.0.1:8000/health>. Check the
browser console and the integrated terminal for connection or server errors.

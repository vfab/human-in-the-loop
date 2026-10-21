# Local Development Guide - HITL Dashboard

## Quick Start (F5)

**The easiest way to run the app:**

1. Open the project in VS Code
2. Press **F5** (or Debug → Start Debugging)
3. The HITL Dashboard will start on http://localhost:8000
4. Open your browser to http://localhost:8000

That's it! The FastAPI server will start with auto-reload enabled, so any changes you make to the code will automatically restart the server.

---

## What F5 Does

When you press F5, VS Code executes the "HITL Dashboard (FastAPI)" debug configuration:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

This:
- ✅ Runs the FastAPI application from `main.py`
- ✅ Enables auto-reload when files change (great for development)
- ✅ Listens on `http://127.0.0.1:8000` (localhost)
- ✅ Attaches the Python debugger so you can set breakpoints
- ✅ Shows output in VS Code's integrated terminal

---

## Available Endpoints

Once the server is running:

| Endpoint | Purpose |
|----------|---------|
| http://localhost:8000 | HITL Dashboard web interface |
| http://localhost:8000/workflows | List available workflows (JSON) |
| http://localhost:8000/health | Server health check |
| http://localhost:8000/docs | FastAPI interactive API docs |
| ws://localhost:8000/ws/workflow/{id}/{run_id} | WebSocket stream for events |

---

## Testing Workflows Locally

1. **Start the server** - Press F5
2. **Open dashboard** - http://localhost:8000
3. **Select a workflow** - Click one of the tabs on the left sidebar
4. **Enter input** (optional) - Some workflows ask for input
5. **Start execution** - Click the "Start" button
6. **Watch events stream** - See agent messages and approvals in real-time

### Available Workflows

| Workflow | Tab Name | Input | What It Does |
|----------|----------|-------|--------------|
| `concurrent` | Concurrent Analysis | Topic to analyze | 3 agents analyze from different perspectives |
| `group_chat` | Group Chat | Discussion topic | Team has a conversation |
| `sequential` | Sequential Review | Document text | Document flows through drafter → editor → finalizer |
| `approval` | Approval Workflow | None | Email assistant processes emails |
| `game` | Guessing Game | None | Agent plays number guessing game |

---

## Debugging

### Setting Breakpoints

1. Click in the gutter next to a line number to set a breakpoint (red circle appears)
2. When that line executes, the debugger will pause
3. Use the Debug toolbar to step through code:
   - **Step Over** (F10) - Execute current line
   - **Step Into** (F11) - Go into function calls
   - **Step Out** (Shift+F11) - Exit current function
   - **Continue** (F5) - Resume execution

### Common Breakpoint Locations

**WebSocket Handler:** `main.py` line 378
```python
async def websocket_workflow_stream(websocket: WebSocket, workflow_id: str, run_id: str):
```

**Event Router:** `main.py` line 457
```python
async for event in workflow_stream:
```

**Workflow Execution:** `main.py` line 410-445
```python
# Different calls for different workflows
if workflow_id == "approval" or workflow_id == "game":
```

---

## Configuration

### Environment Variables (.env)

Create a `.env` file in the project root with Azure OpenAI credentials:

```env
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_API_VERSION=2024-10-21

# Optional for email workflows
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_RECIPIENT=recipient@example.com
```

**Note:** The server will start even without these, but workflows will fail. The dashboard still loads and shows the UI.

### Logging

Logs are printed to the integrated terminal. To see more details:

1. Open `.vscode/settings.json`
2. Set `"python.linting.pylintEnabled": false` if it's too verbose
3. Check `main.py` for `logger = logging.getLogger(__name__)`

---

## Troubleshooting

### "Module not found" errors

**Problem:** `ModuleNotFoundError: No module named 'fastapi'`

**Solution:** Install dependencies
```bash
pip install -r requirements.txt
```

### Port 8000 already in use

**Problem:** `Address already in use` when starting server

**Solution:** Either:
- Kill the process using port 8000 (old server still running)
- Use a different port in launch.json (change `--port 8000` to `--port 8001`)

### WebSocket connection fails

**Problem:** Browser console shows "WebSocket connection error"

**Solution:**
1. Make sure server is running (check terminal)
2. Check `.env` file has valid config (or at least `AZURE_OPENAI_ENDPOINT`)
3. Check browser console for specific error message

### Workflow times out or fails

**Problem:** Workflow doesn't complete or shows error

**Causes:**
- Missing Azure OpenAI credentials in `.env`
- Invalid credentials
- Network issue
- Agent framework version mismatch

**Solution:**
1. Check `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT` in `.env`
2. Check integrated terminal for error messages
3. Set breakpoint in workflow file to debug

---

## Alternative Launch Methods

### Option 1: Debug with F5 (Recommended)

Press F5 - launches with debugger attached

### Option 2: Run without Debugger

Press Ctrl+F5 (or Run → Run Without Debugging) - slightly faster, no debugger

### Option 3: Manual Command Line

```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Option 4: Docker (Production-like)

```bash
docker build -t hitl-dashboard:latest .
docker run -p 8000:8000 hitl-dashboard:latest
```

---

## Making Changes

### Adding a New Workflow

1. Create a new async generator function in `workflows/new_workflow.py`:
```python
async def run_new_workflow(config: WorkflowConfig, user_input: str = "default") -> AsyncIterator[WorkflowEvent]:
    # ... workflow logic
    yield WorkflowEvent(type="agent_message", ...)
```

2. Register it in `main.py` at startup:
```python
_workflow_runners["new_id"] = run_new_workflow
```

3. Add to workflow list in `/workflows` endpoint

4. Add UI tab in `static/index.html`

### Modifying the Dashboard

Edit `static/index.html`, `static/css/style.css`, or `static/js/dashboard.js`

**Note:** CSS and JS are large files (13K+ lines). Changes auto-reload when you save.

### Testing Events

Add temporary logging in `main.py` WebSocket handler:

```python
# Around line 475
logger.info(f"DEBUG: Event type={event_type}, data={event_data}")
```

You'll see the output in the VS Code integrated terminal.

---

## Performance Tips

1. **Disable Pylance (if slow):** Uncheck in Extensions
2. **Reduce auto-reload:** Disable `--reload` in launch.json for production testing
3. **Use just the dashboard:** Don't run demo scripts in compound configs if not needed
4. **Close browser tabs:** Each WebSocket connection uses memory

---

## Next Steps

- 🚀 Try pressing **F5** right now to start the server
- 🌐 Open http://localhost:8000 in your browser
- ⚡ Select a workflow and click "Start"
- 🔍 Watch events stream in real-time
- 🐛 Set breakpoints to debug workflow execution

---

**Last Updated:** 2026-10-20  
**Status:** Production-ready (MVP with auto-approval)

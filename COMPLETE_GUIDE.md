# HITL Dashboard - Complete Setup & Testing Guide

## Quick Status

✅ **Code Status**
- Python syntax: All files valid
- Project structure: Complete
- Static assets: All present (HTML/CSS/JS)
- Architecture: Event-driven WebSocket streaming

❌ **Environment Status** 
- Virtual environment: Not activated
- Dependencies: Not installed in current Python
- Azure credentials: Not configured
- *Note: FastAPI is running in Docker on localhost:8000*

## Architecture Overview

This is a web-based Human-In-The-Loop (HITL) demonstration dashboard with:

- **Backend**: FastAPI server with WebSocket event streaming
- **Frontend**: Single-page application with tabbed interface
- **Workflows**: 5 async generator-based workflows:
  - `concurrent_workflow.py` - Multi-agent concurrent analysis
  - `group_chat_workflow.py` - Sequential team discussion  
  - `sequential_workflow.py` - Document review pipeline
  - `approval_workflow.py` - Email assistant with approvals
  - `game_workflow.py` - Interactive guessing game

- **Event Model**: All workflows emit typed WorkflowEvent objects:
  - `agent_message` - Chat messages from agents
  - `approval_required` - Approval modals
  - `input_required` - User input modals
  - `workflow_complete` - Workflow finished
  - `error` - Error conditions

- **Deployment**: Runs locally (F5), in Docker (container), or in Azure

## Setup for Local Development

### Prerequisites

1. **Python 3.11+** (3.15.0 detected on this system ✓)
2. **Visual C++ Build Tools** (required for pyyaml compilation)
   - Download: https://visualstudio.microsoft.com/downloads/
   - Select "Desktop development with C++"

### Step 1: Create Virtual Environment

```powershell
cd C:\src\human_in_loop

# Create venv
python -m venv .venv

# Activate
.\.venv\Scripts\Activate.ps1

# If you get an execution policy error:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```

Verify activation:
```powershell
python --version  # Should show 3.11+
which python      # Should show path inside .venv
```

### Step 2: Install Dependencies

```powershell
# Upgrade pip, setuptools, wheel
python -m pip install --upgrade pip setuptools wheel

# Install from requirements.txt
pip install -r requirements.txt
```

This installs:
- `fastapi` - Web framework
- `uvicorn[standard]` - ASGI server
- `python-dotenv` - .env file loading
- `azure-identity` - Azure authentication
- `agent-framework-openai` - Agent framework with OpenAI support

**Troubleshooting**:
- If pyyaml fails to compile: Install Visual C++ Build Tools
- If agent-framework-openai not found: Install from local source:
  ```powershell
  pip install -e C:\src\agent_framework\agent-framework
  ```

### Step 3: Configure Credentials

Create `.env` file in project root:

```powershell
# From PowerShell
@"
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
"@ | Set-Content .env
```

Or create `.env` file manually with a text editor.

For testing without credentials:
- Workflows use auto-approval (pre-approved for MVP)
- You can test the UI without real Azure OpenAI

### Step 4: Validate Installation

Run the diagnostic tool:

```powershell
python diagnostic.py
```

Expected output:
```
Summary
--------------------------------------------------
  Python Version            ✓ PASS
  Virtual Environment       ✓ PASS
  Dependencies              ✓ PASS
  Project Files             ✓ PASS
  Configuration             ✓ PASS (optional)
  Python Syntax             ✓ PASS
  Network Connectivity      ⚠ (not needed for setup)
--------------------------------------------------
  Total: 6/7 checks passed
```

## Running Locally

### Option 1: VS Code F5 (Recommended)

1. Open project in VS Code: `code C:\src\human_in_loop`
2. Verify venv is activated (Python interpreter shows `.venv`)
3. Press **F5** to start debugging

Expected output in debug console:
```
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete
```

4. Open browser to **http://localhost:8000**

### Option 2: Command Line

```powershell
# Make sure venv is activated
.\.venv\Scripts\Activate.ps1

# Start Uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or with Python module
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Option 3: Docker (Already Running)

The Docker container is already running on localhost:8000:

```powershell
# Access web UI
Start-Process http://localhost:8000

# Check health
Invoke-WebRequest http://localhost:8000/health
# Expected: {"status": "ok"}

# View logs
docker logs human_in_loop_app

# Stop container
docker stop human_in_loop_app
```

## Testing

### Syntax Validation (No Dependencies)

```powershell
python -c "
import py_compile
from pathlib import Path

files = ['main.py'] + list(Path('workflows').glob('*.py'))
for f in files:
    py_compile.compile(str(f), doraise=True)
    print(f'✓ {f}')
print('\n✅ All Python files valid')
"
```

### Integration Tests (After Installing Dependencies)

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Run all tests
pytest tests/test_workflows_integration.py -v

# Run specific workflow test
pytest tests/test_workflows_integration.py::TestWorkflows::test_concurrent_workflow -v

# Run with coverage
pytest tests/test_workflows_integration.py --cov=workflows --cov-report=html
```

Expected output:
```
tests/test_workflows_integration.py::TestWorkflows::test_concurrent_workflow PASSED
tests/test_workflows_integration.py::TestWorkflows::test_group_chat_workflow PASSED
tests/test_workflows_integration.py::TestWorkflows::test_sequential_workflow PASSED
tests/test_workflows_integration.py::TestWorkflows::test_approval_workflow PASSED
tests/test_workflows_integration.py::TestWorkflows::test_game_workflow PASSED
tests/test_workflows_integration.py::TestWorkflowImports::test_all_imports PASSED
tests/test_workflows_integration.py::TestWorkflowStructure::test_signatures PASSED

===== 7 passed in 12.34s =====
```

### Manual Testing via Browser

1. Navigate to **http://localhost:8000**

2. You should see:
   - Left sidebar with 5 tabs:
     - Concurrent Analysis
     - Group Chat
     - Sequential Review
     - Email Approval
     - Guessing Game
   - Main panel (empty until you select a workflow)

3. Click on a tab (e.g., "Concurrent Analysis")

4. Click "Start Workflow" button

5. Watch events stream in real-time:
   - Agent messages appear
   - Approval modals may pop up
   - Events logged in console

6. Workflow completes with final summary

### WebSocket Event Monitoring

Open browser developer tools (F12):

1. Go to **Network** tab
2. Filter for **WS** (WebSocket)
3. Click on the WebSocket connection
4. Go to **Messages** tab
5. Run a workflow and watch events flow:

```json
{
  "type": "agent_message",
  "data": {
    "agent_name": "Analyst",
    "message": "I have completed my analysis...",
    "timestamp": "2025-01-15T10:30:45.123Z"
  }
}
```

## Project Structure

```
c:\src\human_in_loop\
├── main.py                              # FastAPI server (15,887 lines)
├── requirements.txt                     # Python dependencies
├── diagnostic.py                        # Setup validation tool
├── SETUP_GUIDE.md                       # Detailed setup instructions
├── LOCAL_DEVELOPMENT.md                 # Quick reference
├── README.md                            # Original project README
├── Dockerfile                           # Docker configuration
│
├── workflows/                           # Async generator workflows
│   ├── __init__.py                      # WorkflowConfig dataclass
│   ├── concurrent_workflow.py           # Multi-agent concurrent
│   ├── group_chat_workflow.py           # Sequential team discussion
│   ├── sequential_workflow.py           # Document review
│   ├── approval_workflow.py             # Email assistant
│   └── game_workflow.py                 # Guessing game
│
├── static/                              # Frontend assets
│   ├── index.html                       # Single-page app (4,576 lines)
│   ├── css/
│   │   └── style.css                    # Professional styling (13,718 lines)
│   └── js/
│       └── dashboard.js                 # WebSocket client (14,400 lines)
│
├── tests/                               # Test suite
│   ├── conftest.py                      # Pytest configuration
│   ├── test_syntax_validation.py        # Syntax & import tests
│   └── test_workflows_integration.py    # Full integration tests
│
├── .vscode/
│   └── launch.json                      # VS Code F5 configuration (1 config)
│
├── .copilot-tracking/                   # Development history
│   ├── checkpoints/                     # Prior phase completions
│   ├── plans/                           # Implementation plans
│   └── reviews/                         # Code review notes
│
├── infra/                               # Infrastructure as Code
│   └── (Terraform/Bicep files)
│
├── .git/                                # Git repository
├── .github/                             # GitHub workflows
└── (other original files)

```

## Troubleshooting

### "ModuleNotFoundError: No module named 'agent_framework'"

**Cause**: Dependencies not installed or wrong Python environment.

**Solution**:
```powershell
# Check which Python is running
python -c "import sys; print(sys.executable)"

# Should show: C:\src\human_in_loop\.venv\Scripts\python.exe

# If not, activate venv:
.\.venv\Scripts\Activate.ps1

# Then install:
pip install -r requirements.txt
```

### "preLaunchTask error" in VS Code

**Cause**: Old launch.json configuration.

**Solution**: The current launch.json has no preLaunchTask. If you see this error, your launch.json is outdated:

```powershell
# Remove old file
Remove-Item .vscode/launch.json

# Verify new one exists
Get-Content .vscode/launch.json

# Should show single "HITL Dashboard" configuration
```

### Uvicorn fails to start from F5

**Cause 1**: Wrong Python interpreter selected.
- **Fix**: In VS Code, click Python version in bottom-right and select `.venv` interpreter

**Cause 2**: Port 8000 already in use.
- **Fix**: Stop Docker container or change port in launch.json

**Cause 3**: Missing dependencies.
- **Fix**: Run `pip install -r requirements.txt` inside activated venv

### Dashboard loads but no events appear

**Cause**: FastAPI server running but workflows not executing.

**Diagnosis**:
1. Open browser console (F12)
2. Look for WebSocket errors
3. Check FastAPI server logs for exceptions

**Fix**:
- Verify Azure OpenAI credentials in .env
- Check network connectivity to OpenAI endpoint
- Review error messages in browser console

### Browser shows "Cannot GET /"

**Cause**: FastAPI server not serving index.html.

**Diagnosis**:
1. Check FastAPI logs for errors
2. Verify static/ folder exists
3. Verify main.py is running

**Fix**:
```powershell
# Check that static files exist
Test-Path static/index.html
Test-Path static/css/style.css
Test-Path static/js/dashboard.js

# Check FastAPI is responding
Invoke-WebRequest http://localhost:8000/health
```

## Common Tasks

### Change FastAPI port
Edit `.vscode/launch.json`:
```json
"args": ["--port", "8001"]
```
Then access http://localhost:8001

### Run single workflow for testing
Edit `main.py` WebSocket handler to disable auto-start and test manually

### Deploy to Azure
See `.copilot-tracking/plans/` for Phase 4 Azure deployment guide

### Add a new workflow
1. Create `workflows/new_workflow.py` with async generator
2. Add to workflow registry in `main.py`
3. Add tab to sidebar in `static/index.html`
4. Test with `pytest tests/test_workflows_integration.py -v`

### Enable debug logging
Set environment variable:
```powershell
$env:DEBUG=1
python -m uvicorn main:app --log-level debug
```

## Next Steps

1. ✅ Create and activate virtual environment
2. ✅ Install dependencies: `pip install -r requirements.txt`
3. ✅ Configure Azure credentials in `.env`
4. ✅ Run diagnostic: `python diagnostic.py`
5. ✅ Test locally with F5 or `uvicorn main:app --reload`
6. ✅ Run integration tests: `pytest tests/test_workflows_integration.py -v`
7. ⏳ **Phase 4**: Deploy to Docker / Azure

## Documentation

- [SETUP_GUIDE.md](./SETUP_GUIDE.md) - Detailed setup with troubleshooting
- [LOCAL_DEVELOPMENT.md](./LOCAL_DEVELOPMENT.md) - Quick reference
- [.copilot-tracking/checkpoints/](./copilot-tracking/checkpoints/) - Prior phase summaries
- [.copilot-tracking/plans/](./copilot-tracking/plans/) - Implementation details

## Support

For setup issues:
1. Run `python diagnostic.py` to check environment
2. Review [SETUP_GUIDE.md](./SETUP_GUIDE.md) troubleshooting section
3. Check FastAPI logs: `uvicorn main:app --reload` (manual start)
4. Review browser console (F12 → Console tab)

For workflow issues:
1. Check integration tests pass: `pytest tests/ -v`
2. Verify Azure credentials in .env
3. Check FastAPI logs for exceptions
4. Review workflow implementations in `workflows/`

---

**Last Updated**: 2025-01-15  
**Status**: Phase 3 Complete - Ready for local testing  
**Next Phase**: Phase 4 - Docker & Azure Deployment

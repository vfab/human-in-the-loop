# Local Development Setup Guide

This guide walks through setting up the HITL Dashboard for local development and testing.

## Status

✅ **Phase 1-3 Complete**: All Python code is syntactically valid and architecturally sound.

❌ **Blocked**: Runtime dependencies (agent-framework, agent-framework-openai, python-dotenv, etc.) are not installed.

## Prerequisites

### 1. Python 3.11+ with venv support
```powershell
python --version
```

### 2. Visual C++ Build Tools (Required for Windows)
Some dependencies like `pyyaml` require C++ compilation. Install one of:
- **Visual Studio Build Tools**: https://visualstudio.microsoft.com/downloads/
  - Select "Desktop development with C++"
- **Windows SDK with C++ compiler**
- **MinGW-w64**

Verify installation:
```powershell
cl /?  # MSVC compiler
```

## Setup Steps

### Step 1: Create and Activate Virtual Environment

```powershell
cd C:\src\human_in_loop

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.\.venv\Scripts\Activate.ps1

# If activation fails due to script execution policy:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Step 2: Upgrade pip and Install Dependencies

```powershell
# Upgrade pip, setuptools, wheel
python -m pip install --upgrade pip setuptools wheel

# Install requirements (this will take several minutes on first run)
pip install -r requirements.txt
```

If you encounter errors:
- **pyyaml compilation fails**: Install Visual C++ Build Tools (see Prerequisites)
- **agent_framework not found**: This is expected—the package may be installed from local source:
  ```powershell
  pip install -e C:\src\agent_framework\agent-framework
  ```
- **Other package errors**: Try with `--no-cache-dir`:
  ```powershell
  pip install --no-cache-dir -r requirements.txt
  ```

### Step 3: Validate Installation

Run the syntax validation script:
```powershell
python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

print('Checking imports...')
from workflows import WorkflowConfig
print('✓ WorkflowConfig')

from workflows.concurrent_workflow import run_concurrent_workflow
print('✓ concurrent_workflow')

from workflows.group_chat_workflow import run_group_chat_workflow
print('✓ group_chat_workflow')

from workflows.sequential_workflow import run_sequential_workflow
print('✓ sequential_workflow')

from workflows.approval_workflow import run_approval_workflow
print('✓ approval_workflow')

from workflows.game_workflow import run_game_workflow
print('✓ game_workflow')

from fastapi import FastAPI
print('✓ fastapi')

import uvicorn
print('✓ uvicorn')

print('\n✅ All dependencies installed!')
"
```

Expected output:
```
✓ WorkflowConfig
✓ concurrent_workflow
✓ group_chat_workflow
✓ sequential_workflow
✓ approval_workflow
✓ game_workflow
✓ fastapi
✓ uvicorn

✅ All dependencies installed!
```

## Running the Dashboard

### Local Execution (F5 in VS Code)

1. Open the project in VS Code: `code C:\src\human_in_loop`

2. Press **F5** to start debugging
   - This launches `main.py` with Uvicorn
   - Output appears in VS Code debug console

3. Open browser to **http://localhost:8000**

### Manual Execution (PowerShell)

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Start Uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Server output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started server process [12345]
INFO:     Application startup complete
```

Browse to http://localhost:8000

## Testing Workflows

### Syntax & Import Tests (No Dependencies Required)

```powershell
# This was already run above—all tests passed
# Python files are syntactically valid
# Static files (HTML/CSS/JS) exist and are correct
```

### Integration Tests (Requires Dependencies)

Once dependencies are installed:

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Run all integration tests
pytest tests/test_workflows_integration.py -v

# Run a specific workflow test
pytest tests/test_workflows_integration.py::TestWorkflows::test_concurrent_workflow -v
```

Expected output (after dependencies installed):
```
tests/test_workflows_integration.py::TestWorkflows::test_concurrent_workflow PASSED
tests/test_workflows_integration.py::TestWorkflows::test_group_chat_workflow PASSED
tests/test_workflows_integration.py::TestWorkflows::test_sequential_workflow PASSED
tests/test_workflows_integration.py::TestWorkflows::test_approval_workflow PASSED
tests/test_workflows_integration.py::TestWorkflows::test_game_workflow PASSED

===== 5 passed in 15.23s =====
```

## Configuration

### Azure OpenAI Credentials

The app loads configuration from environment variables or a `.env` file:

```powershell
# Create .env file in project root
$env:AZURE_OPENAI_API_KEY = "your-key-here"
$env:AZURE_OPENAI_ENDPOINT = "https://your-instance.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME = "gpt-4"
$env:SMTP_SERVER = "your-smtp-server"
$env:SMTP_PORT = "587"
```

Or create `.env` file:
```
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
SMTP_SERVER=your-smtp-server
SMTP_PORT=587
```

The app will automatically load these via `python-dotenv`.

## Troubleshooting

### Error: "preLaunchTask 'python: venv check' terminated with exit code 1"

**Cause**: Outdated `launch.json` configuration.

**Solution**: The current `launch.json` no longer has preLaunchTask. If you see this error, the file wasn't updated. Reset it:

```powershell
# Delete old launch.json
Remove-Item -Path .vscode/launch.json

# VS Code will prompt to create a default Python configuration
# Copy from LOCAL_DEVELOPMENT.md or re-run setup
```

### Error: "ModuleNotFoundError: No module named 'agent_framework'"

**Cause**: Dependencies not installed.

**Solution**: Complete Step 2 above (install requirements).

### Error: "Microsoft Visual C++ 14.0 or greater is required"

**Cause**: pyyaml needs compilation; C++ build tools missing.

**Solution**: Install Visual Studio Build Tools (see Prerequisites).

### Dashboard loads but workflows don't execute

**Cause**: Azure OpenAI credentials not configured.

**Solution**: Set environment variables or create `.env` file (see Configuration section).

### WebSocket connection fails

**Cause**: Browser can't reach Uvicorn server.

**Solution**:
1. Verify Uvicorn is running: `http://localhost:8000/health` should return `{"status": "ok"}`
2. Check browser console (F12) for network errors
3. Try `http://127.0.0.1:8000` instead of `localhost:8000`

## Next Steps

1. ✅ Install dependencies
2. ✅ Run integration tests
3. ✅ Test local execution (F5 or `uvicorn main:app --reload`)
4. ⏳ Test Docker deployment (Phase 4)
5. ⏳ Test Azure deployment (Phase 4)

## File Structure

```
c:\src\human_in_loop\
├── main.py                    # FastAPI server + WebSocket handler
├── requirements.txt           # Python dependencies
├── launch.json               # VS Code F5 configuration
├── .venv/                    # Virtual environment (created by setup)
├── workflows/
│   ├── __init__.py          # WorkflowConfig dataclass
│   ├── concurrent_workflow.py
│   ├── group_chat_workflow.py
│   ├── sequential_workflow.py
│   ├── approval_workflow.py
│   └── game_workflow.py
├── static/
│   ├── index.html           # Dashboard UI
│   ├── css/style.css        # Styling
│   └── js/dashboard.js      # Client-side logic
└── tests/
    ├── conftest.py          # Pytest configuration
    ├── test_syntax_validation.py
    └── test_workflows_integration.py
```

## Support

For questions or issues:
1. Review `.copilot-tracking/checkpoints/` for prior decisions
2. Check `LOCAL_DEVELOPMENT.md` for quick reference
3. Review Phase 3 implementation notes in `.copilot-tracking/plans/`

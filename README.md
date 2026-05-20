# Human-in-the-Loop (HITL) Agent Workflows

This repository contains sample workflows demonstrating human-in-the-loop patterns with the Microsoft Agent Framework. These samples show how to pause AI agent execution to collect human feedback, make decisions, or provide guidance before the agent continues its work.

## Overview

Human-in-the-loop (HITL) workflows integrate AI agents with human decision-making at critical points. This repository provides multiple examples showing different HITL patterns:

- **Sequential workflows** with human input before specific agents speak
- **Concurrent workflows** with human review of individual agent outputs before aggregation
- **Approval-based workflows** for sensitive operations requiring human approval
- **Interactive games** demonstrating alternating turns between agent and human
- **Email assistant** showing practical application with email processing and response

## Prerequisites

- **Python 3.12.3** or later
- **Azure OpenAI** service configured and accessible
- **Azure CLI** installed and authenticated (`az login`)
- **Docker** (for containerized deployment)
- **Terraform** (for Azure infrastructure deployment)

### Environment Setup

1. Install Python dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Configure environment variables in `.env`:
   ```env
   AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
   AZURE_OPENAI_API_KEY=<your-api-key>
   AZURE_OPENAI_CHAT_MODEL=<your-model-deployment-name>
   # Optional fallback used by samples:
   # AZURE_OPENAI_MODEL=<your-model-deployment-name>
   ```

3. Authenticate with Azure:
   ```bash
   az login
   ```

## Sample Workflows

### 1. Guessing Game with Human Input
**File:** `guessing_game_with_human_input.py`

An interactive game where an AI agent guesses a number and a human provides feedback (higher, lower, or correct). Demonstrates alternating turns between agent and human using the request info API.

**Run:**
```bash
python guessing_game_with_human_input.py
```

### 2. Sequential Request Info
**File:** `sequential_request_info.py`

A sequential workflow that pauses before specific agents respond, allowing human input to steer their answers. Shows how to use agent filtering to reduce interruptions.

**Run:**
```bash
python sequential_request_info.py
```

### 3. Concurrent Request Info
**File:** `concurrent_request_info.py`

A concurrent workflow where multiple agents run in parallel. Pauses for human review of individual agent outputs before they are aggregated.

**Run:**
```bash
python concurrent_request_info.py
```

### 4. Group Chat with Request Info
**File:** `group_chat_request_info.py`

A sequential group chat style workflow demonstrating selective pausing before specific participants speak. Shows how to inject human input to steer agent behavior in multi-agent conversations.

**Run:**
```bash
python group_chat_request_info.py
```

### 5. Email Assistant with Approval Requests
**File:** `agents_with_approval_requests.py`

An email assistant workflow that processes incoming emails and requires human approval for sensitive operations. Demonstrates practical HITL integration with external systems.

**Run:**
```bash
python agents_with_approval_requests.py
```

## API Server

### FastAPI Application
**File:** `app_server.py`

A FastAPI-based HTTP server exposing the email assistant workflow.

**Endpoints:**

- **GET `/health`** — Health check endpoint
  ```bash
  curl http://localhost:8000/health
  ```

- **POST `/run`** — Run the email assistant workflow
  ```bash
   curl -X POST http://localhost:8000/run \
      -H "Content-Type: application/json" \
      -d '{
         "sender": "sam@example.com",
         "subject": "Urgent: Agent Framework Review Required",
         "body": "Please review the latest agent framework updates and share feedback by end of week."
      }'
  ```

**Running the Server:**
```bash
uvicorn app_server:app --host 0.0.0.0 --port 8000
```

For development with auto-reload:
```bash
uvicorn app_server:app --reload
```

## Deployment

### Local Docker Deployment

1. Build the Docker image:
   ```bash
   docker build -t hitl-workflows:latest .
   ```

2. Run the container:
   ```bash
   docker run -p 8000:8000 \
     -e AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT \
     -e AZURE_OPENAI_API_KEY=$AZURE_OPENAI_API_KEY \
      -e AZURE_OPENAI_CHAT_MODEL=$AZURE_OPENAI_CHAT_MODEL \
     hitl-workflows:latest
   ```

### Azure Deployment with Terraform

This repository includes Terraform infrastructure for deploying:
- Backend API to Azure Container Apps
- Frontend to Azure Static Web Apps

The Terraform code is designed to use existing shared resources in `rg-vfab`:
- ACR: `ca81b3cb0669acr`
- Container Apps environment: `vfab-container-env`

**Manual deploy:**
```bash
cd infra
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

### CI/CD Deployment (GitHub Actions)

Workflow file: `.github/workflows/deploy-azure-terraform.yml`

The workflow:
1. Authenticates to Azure using OIDC
2. Builds and pushes the backend Docker image to ACR
3. Runs `terraform init`, `terraform validate`, `terraform plan`, and `terraform apply`
4. Prints deployment outputs

Required GitHub repository secrets:
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_OPENAI_API_KEY`

Recommended GitHub repository variables:
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_CHAT_MODEL`
- `AZURE_OPENAI_API_VERSION`

## Repository Structure

```
.
├── agents_with_approval_requests.py      # Email assistant with approval workflow
├── concurrent_request_info.py             # Concurrent agent workflow with human review
├── group_chat_request_info.py             # Group chat style sequential workflow
├── guessing_game_with_human_input.py      # Interactive guessing game
├── sequential_request_info.py             # Sequential workflow with request info
├── app_server.py                          # FastAPI HTTP server
├── requirements.txt                       # Python dependencies
├── Dockerfile                             # Container image definition
├── .env                                   # Environment variables (not committed)
├── .env.example                           # Example environment configuration
├── .gitignore                             # Git ignore rules
├── .github/workflows/                     # CI/CD workflows
│   ├── python-tests.yml                   # Unit test workflow
│   └── deploy-azure-terraform.yml         # Terraform deployment workflow
├── infra/                                 # Terraform infrastructure code
│   ├── main.tf                            # Main infrastructure resources
│   ├── variables.tf                       # Variable definitions
│   ├── outputs.tf                         # Output values
│   ├── providers.tf                       # Provider configuration
│   └── terraform.tfvars.example           # Example variable values
└── .specify/                              # Spec Kit configuration
    └── extensions/git/                    # Git branching workflow extension
```

## Key Concepts

### Request Info API

The `request_info` API allows workflows to pause and request external input:

```python
# Pause workflow and request human input
ctx.request_info(payload=HumanFeedbackRequest(...))

# Continue workflow with responses
workflow.run(responses=[...], stream=True)
```

### WorkflowBuilder Patterns

- **SequentialBuilder** — Agents run one after another
- **ConcurrentBuilder** — Multiple agents run in parallel
- **GroupChatBuilder** — Multi-agent conversation with sequential turns

### Event Handling

Workflows emit events that applications can handle:

```python
async for event in workflow.run_stream():
    if event.type == "request_info":
        # Handle pause and request human input
        pass
```

## Dependencies

- **agent-framework-openai** ≥ 1.4.0 — Microsoft Agent Framework with OpenAI integration
- **python-dotenv** ≥ 1.0.1 — Environment variable loading
- **azure-identity** ≥ 1.17.1 — Azure authentication
- **fastapi** ≥ 0.112.0 — HTTP API framework
- **uvicorn** ≥ 0.30.6 — ASGI server

## Contributing

When adding new workflows or modifications:

1. Create a feature branch: `git checkout -b feature/my-workflow`
2. Follow the existing code style and patterns
3. Add docstrings explaining the workflow purpose and pattern
4. Test locally before committing
5. Submit a pull request with a clear description

## License

Copyright (c) Microsoft. All rights reserved.

Licensed under the MIT License. See LICENSE file for details.

## Support

For issues, questions, or feedback:
- Check existing issues in the repository
- Review the Agent Framework documentation
- Refer to Azure OpenAI documentation

## Resources

- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- [Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Terraform Documentation](https://www.terraform.io/docs)

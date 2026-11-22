---
title: Human-in-the-Loop Demo Applications
description: Overview and documentation index for the human-in-the-loop workflow dashboard and Python examples
---

This repository contains Python agent-framework examples and a FastAPI dashboard
for human-in-the-loop workflows.

## Documentation

* [Local development guide](LOCAL_DEVELOPMENT.md): Windows setup, local
  configuration, launch, testing, and troubleshooting
* [Container authentication guide](CONTAINER_AUTH.md): container configuration,
  Azure OpenAI credentials, and deployment authentication limitations

The guides are the sources of truth for setup and authentication details. This
README intentionally keeps only an overview to avoid duplicating instructions.

## Project Overview

The dashboard serves a browser interface and streams workflow events over
WebSockets. The application code is in `main.py` and `workflows/`; frontend
assets are in `static/`, tests are in `tests/`, and Terraform deployment
configuration is in `infra/`.

The registered workflows are concurrent analysis, group chat, sequential
review, approval, guessing game, handoff, and Magentic orchestration. Workflow
execution requires valid Azure OpenAI configuration and authentication.

## Requirements

* Python 3.10 or later
* Azure CLI for local Azure CLI authentication
* Docker Desktop and Terraform 1.6 or later for container deployment

## License

Microsoft - All rights reserved

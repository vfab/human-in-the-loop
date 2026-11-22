---
title: Container Authentication Guide
description: Configure Azure OpenAI credentials and secrets for container deployments
---

## Authentication Support

The workflows authenticate to Azure OpenAI with `AzureCliCredential` when
`AZURE_OPENAI_API_KEY` is unset, or with the configured API key when it is set.
All workflows use this credential selection in their Azure OpenAI clients.

The Terraform configuration supplies `AZURE_OPENAI_API_KEY` to the Container
App as a secret. The current application and Terraform configuration do not
configure a managed identity for Azure OpenAI authentication. Do not rely on
`DefaultAzureCredential`, managed identity, or Key Vault integration unless the
application and deployment configuration are updated to support them.

For local setup and Azure CLI authentication, see the
[local development guide](LOCAL_DEVELOPMENT.md).

## Container Configuration

Set the following runtime values when deploying the Container App:

* `AZURE_OPENAI_ENDPOINT`: Azure OpenAI resource endpoint
* `AZURE_OPENAI_CHAT_MODEL` or `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: deployed
  model name
* `AZURE_OPENAI_API_VERSION`: API version; the application default is
  `2024-10-21`
* `AZURE_OPENAI_API_KEY`: Azure OpenAI key, provided as a container secret

The Terraform variables are declared in `infra/variables.tf`. Supply sensitive
values through the approved deployment secret mechanism; do not put real keys
in source files, command history, or committed Terraform variable files. The
Terraform deployment also requires Azure CLI authentication for provisioning
and access to the configured remote state and shared resources.

To deploy, configure `infra/backend.hcl` from its example, initialize and
validate Terraform, build and publish the image, then review and apply a
Terraform plan. Confirm the subscription, target resources, image tag, and
secret values before applying.

## Email Workflow Secrets

Email workflows read SMTP configuration from environment variables:
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `EMAIL_RECIPIENT`.
Provide credentials using the deployment platform's secret facility. These
settings are optional unless the email workflow is being used.

## Local Container Testing

Build and run the image without placing credentials in the Dockerfile:

```powershell
docker build -t hitl-dashboard:test .
docker run --rm -p 8000:8000 `
  -e AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/" `
  -e AZURE_OPENAI_CHAT_MODEL="<your-deployment>" `
  -e AZURE_OPENAI_API_KEY `
  hitl-dashboard:test
```

Set the key in the local environment using a secure method before running the
command. Never put credentials in the command text, Dockerfile, or repository.

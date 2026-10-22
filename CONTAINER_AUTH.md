# Container Authentication & Secrets Management

This guide explains how to authenticate the HITL Dashboard in Azure Container Apps using managed identities and Azure Key Vault secrets.

## Overview

The HITL Dashboard supports two authentication patterns:

1. **Local Development:** `AzureCliCredential` (via `az login`)
2. **Container Apps (Production):** `DefaultAzureCredential` + Azure Key Vault

## Local Development Setup

### Prerequisites

```bash
# Install Azure CLI
# https://learn.microsoft.com/cli/azure/install-azure-cli

# Authenticate
az login

# Verify you can access the target subscription
az account show
```

### Environment Variables (.env)

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Fill in your values:

```env
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_CHAT_MODEL=gpt-4o
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# Leave these unset to use AzureCliCredential (az login)
# AZURE_OPENAI_API_KEY=

# Optional: Email workflow settings
EMAIL_RECIPIENT=your-email@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-gmail@gmail.com
SMTP_PASSWORD=your-app-password  # See: https://support.google.com/accounts/answer/185833
```

**Note:** Gmail app passwords may contain spaces; the code automatically strips them.

### Running Locally

```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run the dashboard
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# Open http://127.0.0.1:8000
```

The app will use:
- `az login` credentials for Azure OpenAI API calls
- Environment variables for SMTP/email settings (if configured)

## Container Apps Deployment

### Architecture

```
Azure Container Apps
    ↓
Application (Docker container)
    ↓ (requests API via TLS)
Azure OpenAI
    ↓ (authenticate with managed identity + Key Vault)
```

### Authentication Flow

1. **Container App has a managed identity** (system-assigned or user-assigned)
2. **Identity has RBAC roles** on Azure OpenAI and Key Vault
3. **Application uses `DefaultAzureCredential`** which tries:
   - Environment variables (for local testing)
   - Managed identity (in Azure Container Apps)
   - Azure CLI credentials (fallback for development)

### Environment Variables (Container Apps)

Set these via **Secrets** in Azure Container Apps environment:

#### Required Secrets (from Key Vault)

| Name | Value | Source |
|------|-------|--------|
| `AZURE_OPENAI_ENDPOINT` | `https://vfab2-openai.openai.azure.com/` | Azure OpenAI resource URL |
| `AZURE_OPENAI_CHAT_MODEL` | `gpt-4o` | Deployment name |
| `AZURE_OPENAI_API_VERSION` | `2024-12-01-preview` | API version string |

#### Optional Secrets (for email workflows)

| Name | Value | Source |
|------|-------|--------|
| `EMAIL_RECIPIENT` | `alerts@company.com` | Destination email address |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server (Gmail shown) |
| `SMTP_PORT` | `465` | SMTP port (587 for TLS, 465 for SSL) |
| `SMTP_USER` | `noreply@gmail.com` | Service account email |
| `SMTP_PASSWORD` | `xxxx xxxx xxxx xxxx` | Gmail app password or secret |

### Azure Key Vault Setup

1. **Create or use existing Key Vault** (e.g., `kv-vfab`)

2. **Store secrets**:
   ```bash
   az keyvault secret set \
     --vault-name kv-vfab \
     --name SmtpPassword \
     --value "<your-app-password>"

   az keyvault secret set \
     --vault-name kv-vfab \
     --name EmailRecipient \
     --value "<your-email@example.com>"
   ```

3. **Grant managed identity access**:
   ```bash
   # Get the managed identity ID
   az containerapp identity show \
     --name hitl-dashboard \
     --resource-group rg-vfab

   # Assign "Key Vault Secrets User" role
   az role assignment create \
     --role "Key Vault Secrets User" \
     --assignee <identity-object-id> \
     --scope /subscriptions/<sub-id>/resourceGroups/rg-vfab/providers/Microsoft.KeyVault/vaults/kv-vfab
   ```

### Azure OpenAI RBAC

The managed identity also needs **Cognitive Services OpenAI User** role on the Azure OpenAI resource:

```bash
az role assignment create \
  --role "Cognitive Services OpenAI User" \
  --assignee <identity-object-id> \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-vfab/providers/Microsoft.CognitiveServices/accounts/vfab2-openai
```

### Container App Configuration (Terraform)

The Container App should be configured with:

```hcl
resource "azurerm_container_app" "hitl_dashboard" {
  name                         = "hitl-dashboard"
  container_app_environment_id = azurerm_container_app_environment.cae.id
  resource_group_name          = azurerm_resource_group.hitl.name

  identity {
    type = "SystemAssigned"  # or UserAssigned
  }

  template {
    container {
      image = "acrvfab.azurecr.io/hitl-dashboard:latest"
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = "https://vfab2-openai.openai.azure.com/"
      }
      env {
        name  = "AZURE_OPENAI_CHAT_MODEL"
        value = "gpt-4o"
      }
      env {
        name        = "SMTP_PASSWORD"
        secret_name = "smtp-password"  # Maps to Key Vault secret
      }
    }
    scale {
      min_replicas = 1
      max_replicas = 5
    }
  }

  secret {
    name  = "smtp-password"
    value = data.azurerm_key_vault_secret.smtp_password.value
  }
}
```

### Environment Variable Mapping

Container Apps allows secrets to be mounted as environment variables:

| Container App Secret | Maps to Env Var | Key Vault |
|----------------------|-----------------|-----------|
| `smtp-password` | `SMTP_PASSWORD` | `SmtpPassword` |
| `email-recipient` | `EMAIL_RECIPIENT` | `EmailRecipient` |

**Note:** Azure OpenAI endpoint and model can be stored in Key Vault or configured as plain environment variables (they're not sensitive).

## Credential Resolution Order (DefaultAzureCredential)

When running in Azure Container Apps:

1. **Environment variables** (`AZURE_OPENAI_API_KEY` if set)
2. **Managed identity** (system-assigned or user-assigned)
3. **Azure CLI** (if running locally with `az login`)
4. **Visual Studio** (if debugging locally)
5. **Fail** with `DefaultAzureCredential: failed to acquire a token`

For the HITL Dashboard:

- **No `AZURE_OPENAI_API_KEY` env var** → Uses managed identity in Container Apps
- **Local dev** → Falls through to Azure CLI credentials (requires `az login`)

## Testing Container Locally

### Option 1: Docker Run (with az login forwarding)

```bash
# Build image
docker build -t hitl-dashboard:test .

# Run with local az credentials
docker run \
  -v $env:USERPROFILE\.azure:/root/.azure:ro \
  -p 8000:8000 \
  --env AZURE_OPENAI_ENDPOINT=https://vfab2-openai.openai.azure.com/ \
  --env AZURE_OPENAI_CHAT_MODEL=gpt-4o \
  --env EMAIL_RECIPIENT=test@example.com \
  hitl-dashboard:test
```

**Note:** This only works on Windows with Docker for Windows; Docker Desktop manages the mount.

### Option 2: Docker Run (with API key for testing)

```bash
docker run \
  -p 8000:8000 \
  --env AZURE_OPENAI_API_KEY="..." \
  --env AZURE_OPENAI_ENDPOINT=https://vfab2-openai.openai.azure.com/ \
  --env AZURE_OPENAI_CHAT_MODEL=gpt-4o \
  --env SMTP_PASSWORD="..." \
  hitl-dashboard:test
```

**⚠️ Do not commit API keys to git or Dockerfile.**

## Troubleshooting

### "DefaultAzureCredential did not attempt to use local development credentials"

**Cause:** Running in a container without a managed identity and no environment variables set.

**Solution:**
- In Container Apps: Assign a managed identity and grant RBAC roles
- Local testing: Use `--env AZURE_OPENAI_API_KEY` or mount Azure CLI credentials

### "Key not found in the vault"

**Cause:** Managed identity doesn't have "Key Vault Secrets User" role.

**Solution:**
```bash
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee <identity-object-id> \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-vfab/providers/Microsoft.KeyVault/vaults/kv-vfab
```

### "Insufficient privileges to complete the operation"

**Cause:** Managed identity doesn't have the right role on Azure OpenAI.

**Solution:**
```bash
az role assignment create \
  --role "Cognitive Services OpenAI User" \
  --assignee <identity-object-id> \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-vfab/providers/Microsoft.CognitiveServices/accounts/vfab2-openai
```

## Migration Checklist

- [ ] All workflows updated to support `DefaultAzureCredential`
- [ ] `.env.example` documents ACA environment variable names
- [ ] Key Vault created with required secrets
- [ ] Managed identity assigned to Container App
- [ ] RBAC roles assigned to managed identity
- [ ] Terraform code includes secret references
- [ ] Local `.env` file is in `.gitignore` (confirmed)
- [ ] No API keys in git history (verified with `git log` and `git show`)
- [ ] Container App deployment tested with managed identity
- [ ] Smoke tests run against deployed container

## References

- [Azure Identity library (Python)](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/identity/azure-identity)
- [DefaultAzureCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential?view=azure-python)
- [Azure Container Apps secrets](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets?tabs=arm-template)
- [Key Vault access with managed identity](https://learn.microsoft.com/en-us/azure/key-vault/general/assign-access-policy)

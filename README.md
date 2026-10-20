# Human-in-the-Loop Demo Applications

A collection of Python agent framework examples demonstrating human-in-the-loop workflows for concurrent and sequential agent coordination.

## Setup

### Prerequisites

- Python 3.10+
- Azure CLI (`az login` configured)
- Docker Desktop (for container deployment)
- Terraform 1.6+

### Local Development (Windows)

1. **Create and activate virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Verify installation:**
   ```powershell
   python -m py_compile *.py
   ```

4. **Run the app server:**
   ```powershell
   uvicorn app_server:app --port 8000
   ```

   The API will be available at `http://localhost:8000/`

### Azure Deployment

#### Prerequisites

- Azure subscription with `ba1e5722-3386-4ff8-be48-64c548b8756f` ID
- Access to shared resources in `rg-vfab`
- Docker credentials configured for `acrba1e5722.azurecr.io`

#### Terraform Setup

1. **Initialize Terraform backend:**
   ```powershell
   cd infra
   cp backend.hcl.example backend.hcl
   # Edit backend.hcl if needed (defaults are pre-configured)
   terraform init -backend-config=backend.hcl
   ```

2. **Validate configuration:**
   ```powershell
   terraform fmt -check
   terraform validate
   ```

3. **Build and push container image:**
   ```powershell
   az acr login -n acrba1e5722
   $IMAGE_TAG="acrba1e5722.azurecr.io/hitl-email-assistant:$(git rev-parse --short HEAD)"
   docker build -t $IMAGE_TAG .
   docker push $IMAGE_TAG
   ```

4. **Plan deployment:**
   ```powershell
   # Set required variables
   $env:TF_VAR_subscription_id = "ba1e5722-3386-4ff8-be48-64c548b8756f"
   $env:TF_VAR_container_image = "$IMAGE_TAG"
   $env:TF_VAR_azure_openai_endpoint = "https://<your-openai>.openai.azure.com/"
   $env:TF_VAR_azure_openai_chat_model = "gpt-4o"
   $env:TF_VAR_azure_openai_api_key = "<your-api-key>"
   
   terraform plan -out=tfplan
   ```

5. **Apply deployment:**
   ```powershell
   terraform apply tfplan
   ```

   Outputs will include the Container App URL.

## Architecture

The deployment uses:

- **Shared Foundation (rg_vfab_terraform):**
  - Azure Container Registry (`acrba1e5722`)
  - Container Apps Environment (`vfab-cae`) in eastus2
  - Log Analytics Workspace (`vfab-log-analytics`)
  - Resource Group (`rg-vfab`) in eastus

- **This Repository:**
  - Container App (`hitl-email-assistant`) running the FastAPI server
  - Email Communication Service (`vfab-hitl-email`) for sending emails
  - Terraform state in blob storage (`human-in-the-loop-tfstate`)

## State Management

Terraform state is stored in Azure Blob Storage:
- **Account:** `tfstateba1e5722`
- **Container:** `human-in-the-loop-tfstate`
- **Authentication:** Azure AD (configure via `az login`)

## Environment Variables

### Runtime

- `AZURE_OPENAI_ENDPOINT`: Azure OpenAI service endpoint URL
- `AZURE_OPENAI_CHAT_MODEL`: Model deployment name (e.g., `gpt-4o`)
- `AZURE_OPENAI_API_VERSION`: OpenAI API version (default: `2024-12-01-preview`)
- `AZURE_OPENAI_API_KEY`: OpenAI API key (provided via secrets)

### Terraform

All terraform variables can be set via environment variables with `TF_VAR_` prefix:
- `TF_VAR_subscription_id`
- `TF_VAR_container_image`
- `TF_VAR_azure_openai_endpoint`
- `TF_VAR_azure_openai_chat_model`
- `TF_VAR_azure_openai_api_key` (sensitive)

## Troubleshooting

### Terraform Backend Connection Issues

If you see auth errors during `terraform init`:

```powershell
# Ensure Azure CLI is authenticated
az login

# Check subscription
az account show

# Verify storage account access
az storage account show -n tfstateba1e5722 -g rg-vfab
```

### Container Build Failures

```powershell
# Clear Docker cache if needed
docker builder prune

# Rebuild with no cache
docker build --no-cache -t $IMAGE_TAG .
```

### Container App Deployment Issues

```powershell
# Verify logs
$APP_NAME = "hitl-email-assistant"
az containerapp logs show -n $APP_NAME -g rg-vfab
```

## License

Microsoft - All rights reserved

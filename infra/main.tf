# App-level infrastructure only.
# Shared rg-vfab foundation resources (RG/ACR/Container Apps Environment/Log Analytics)
# are managed in ~/src/rg-vfab-terraform/shared.

data "terraform_remote_state" "shared" {
  count   = var.shared_remote_state_enabled ? 1 : 0
  backend = "local"
  config = {
    path = var.shared_remote_state_path
  }
}

data "azurerm_client_config" "current" {}

locals {
  shared_rg_name       = var.shared_remote_state_enabled ? data.terraform_remote_state.shared[0].outputs.resource_group_name : var.resource_group_name
  shared_acr_name      = var.shared_remote_state_enabled ? data.terraform_remote_state.shared[0].outputs.acr_name : var.acr_name
  shared_container_env = var.shared_remote_state_enabled ? data.terraform_remote_state.shared[0].outputs.container_env_name : var.container_env_name

  effective_openai_endpoint    = coalesce(var.foundry_openai_endpoint, var.azure_openai_endpoint)
  effective_openai_deployment  = coalesce(var.foundry_openai_deployment, var.azure_openai_chat_model)
  effective_openai_api_version = coalesce(var.foundry_openai_api_version, var.azure_openai_api_version, "2024-12-01-preview")
  effective_openai_api_key     = coalesce(var.foundry_openai_api_key, var.azure_openai_api_key)
}

resource "azurerm_email_communication_service" "email" {
  name                = var.acs_email_service_name
  resource_group_name = data.azurerm_resource_group.target.name
  data_location       = var.acs_data_location
}

resource "azurerm_email_communication_service_domain" "managed" {
  name             = "AzureManagedDomain"
  email_service_id = azurerm_email_communication_service.email.id
  domain_management = "AzureManaged"
}

resource "azurerm_communication_service" "acs" {
  name                = var.acs_name
  resource_group_name = data.azurerm_resource_group.target.name
  data_location       = var.acs_data_location
}

resource "azurerm_communication_service_email_domain_association" "managed" {
  communication_service_id = azurerm_communication_service.acs.id
  email_service_domain_id  = azurerm_email_communication_service_domain.managed.id
}

data "azurerm_resource_group" "target" {
  name = local.shared_rg_name
}

data "azurerm_container_app_environment" "target" {
  name                = local.shared_container_env
  resource_group_name = data.azurerm_resource_group.target.name
}

data "azurerm_container_registry" "target" {
  name                = local.shared_acr_name
  resource_group_name = data.azurerm_resource_group.target.name
}

data "azurerm_key_vault" "model_secrets" {
  count               = var.key_vault_name != null ? 1 : 0
  name                = var.key_vault_name
  resource_group_name = data.azurerm_resource_group.target.name
}

resource "azurerm_container_app" "backend" {
  name                         = var.backend_name
  resource_group_name          = data.azurerm_resource_group.target.name
  container_app_environment_id = data.azurerm_container_app_environment.target.id
  revision_mode                = "Single"

  registry {
    server               = data.azurerm_container_registry.target.login_server
    username             = data.azurerm_container_registry.target.admin_username
    password_secret_name = "acr-admin-password"
  }

  secret {
    name  = "acr-admin-password"
    value = data.azurerm_container_registry.target.admin_password
  }

  dynamic "secret" {
    for_each = var.key_vault_name == null ? [1] : []
    content {
      name  = "azure-openai-api-key"
      value = local.effective_openai_api_key
    }
  }

  # Prefer Key Vault reference so the API key value is not materialized in
  # Terraform state or deployment logs. The backend's system-assigned identity
  # must have secret get/list permissions on this vault.
  dynamic "secret" {
    for_each = var.key_vault_name != null ? [1] : []
    content {
      name                = "azure-openai-api-key"
      key_vault_secret_id = "${data.azurerm_key_vault.model_secrets[0].vault_uri}secrets/${var.openai_api_key_secret_name}"
      identity            = "System"
    }
  }

  secret {
    name  = "acs-connection-string"
    value = azurerm_communication_service.acs.primary_connection_string
  }

  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "backend"
      image  = var.container_image
      cpu    = var.container_cpu
      memory = var.container_memory

      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = local.effective_openai_endpoint
      }

      env {
        name  = "AZURE_OPENAI_CHAT_MODEL"
        value = local.effective_openai_deployment
      }

      env {
        name  = "AZURE_OPENAI_API_VERSION"
        value = local.effective_openai_api_version
      }

      env {
        name        = "AZURE_OPENAI_API_KEY"
        secret_name = "azure-openai-api-key"
      }

      env {
        name  = "FOUNDRY_OPENAI_ENDPOINT"
        value = local.effective_openai_endpoint
      }

      env {
        name  = "FOUNDRY_OPENAI_DEPLOYMENT"
        value = local.effective_openai_deployment
      }

      env {
        name  = "FOUNDRY_OPENAI_API_VERSION"
        value = local.effective_openai_api_version
      }

      env {
        name        = "FOUNDRY_OPENAI_API_KEY"
        secret_name = "azure-openai-api-key"
      }

      env {
        name  = "ACS_EMAIL_SENDER_ADDRESS"
        value = var.acs_email_sender_address
      }

      env {
        name        = "ACS_CONNECTION_STRING"
        secret_name = "acs-connection-string"
      }

      env {
        name  = "AZURE_APP_CONFIG_ENDPOINT"
        value = azurerm_app_configuration.config.endpoint
      }
    }
  }
}

# Grant the Container App's system-assigned identity read access to Key Vault
# secrets when Key Vault-backed model keys are used.
#
# Fallback behavior:
# - Policy mode vaults: use access policy with Get/List secret permissions.
# - RBAC mode vaults: use built-in "Key Vault Secrets User" role assignment.
resource "azurerm_key_vault_access_policy" "backend_model_secrets" {
  count        = var.key_vault_name != null && !data.azurerm_key_vault.model_secrets[0].rbac_authorization_enabled ? 1 : 0
  key_vault_id = data.azurerm_key_vault.model_secrets[0].id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_container_app.backend.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

resource "azurerm_role_assignment" "backend_model_secrets_rbac" {
  count                = var.key_vault_name != null && data.azurerm_key_vault.model_secrets[0].rbac_authorization_enabled ? 1 : 0
  scope                = data.azurerm_key_vault.model_secrets[0].id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.backend.identity[0].principal_id
}

resource "azurerm_static_web_app" "frontend" {
  name                = var.frontend_name
  resource_group_name = data.azurerm_resource_group.target.name
  location            = var.frontend_location
  sku_tier            = "Standard"
  sku_size            = "Standard"
}

# ─── Azure App Configuration ───────────────────────────────────────────────

resource "azurerm_app_configuration" "config" {
  name                = var.app_config_name
  resource_group_name = data.azurerm_resource_group.target.name
  location            = var.location
  sku                 = "free"
}

# Role assignment is managed manually via az CLI (requires Owner/UAA privileges)
# az role assignment create --role "App Configuration Data Reader" \
#   --assignee <principal_id> --scope <app_config_id>

# App Configuration keys are managed via az CLI (avoids slow Terraform provider):
# az appconfig kv set --name vfab-hitl-appconfig --key hitl/invoice/cost-limit --value "1000" --yes
# az appconfig kv set --name vfab-hitl-appconfig --key hitl/invoice/days-limit --value "30" --yes
# az appconfig kv set --name vfab-hitl-appconfig --key hitl/invoice/approved-vendors --value '[...]' --yes
# az appconfig kv set --name vfab-hitl-appconfig --key hitl/support/auto-resolve-categories --value '[...]' --yes
# az appconfig kv set --name vfab-hitl-appconfig --key hitl/support/escalation-keywords --value '[...]' --yes

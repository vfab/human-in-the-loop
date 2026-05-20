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

locals {
  shared_rg_name       = var.shared_remote_state_enabled ? data.terraform_remote_state.shared[0].outputs.resource_group_name : var.resource_group_name
  shared_acr_name      = var.shared_remote_state_enabled ? data.terraform_remote_state.shared[0].outputs.acr_name : var.acr_name
  shared_container_env = var.shared_remote_state_enabled ? data.terraform_remote_state.shared[0].outputs.container_env_name : var.container_env_name
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

  secret {
    name  = "azure-openai-api-key"
    value = var.azure_openai_api_key
  }

  secret {
    name  = "acs-connection-string"
    value = azurerm_communication_service.acs.primary_connection_string
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
        value = var.azure_openai_endpoint
      }

      env {
        name  = "AZURE_OPENAI_CHAT_MODEL"
        value = var.azure_openai_chat_model
      }

      env {
        name  = "AZURE_OPENAI_API_VERSION"
        value = var.azure_openai_api_version
      }

      env {
        name        = "AZURE_OPENAI_API_KEY"
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
    }
  }
}

resource "azurerm_static_web_app" "frontend" {
  name                = var.frontend_name
  resource_group_name = data.azurerm_resource_group.target.name
  location            = var.frontend_location
  sku_tier            = "Standard"
  sku_size            = "Standard"
}

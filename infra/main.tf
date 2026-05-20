# App-level infrastructure only.
# Shared rg-vfab foundation resources (RG/ACR/Container Apps Environment/Log Analytics)
# are managed in ~/src/rg-vfab-terraform/shared.

data "azurerm_resource_group" "target" {
  name = var.resource_group_name
}

data "azurerm_container_app_environment" "target" {
  name                = var.container_env_name
  resource_group_name = var.resource_group_name
}

data "azurerm_container_registry" "target" {
  name                = var.acr_name
  resource_group_name = var.resource_group_name
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

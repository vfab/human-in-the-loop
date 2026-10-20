locals {
  app_name = "hitl-email-assistant"
}

data "azurerm_client_config" "current" {}

resource "azurerm_container_app" "this" {
  name                         = local.app_name
  container_app_environment_id = data.azurerm_container_app_environment.main.id
  resource_group_name          = data.azurerm_resource_group.main.name
  revision_mode                = "Single"

  registry {
    server               = data.azurerm_container_registry.main.login_server
    username             = data.azurerm_container_registry.main.admin_username
    password_secret_name = "acr-admin-password"
  }

  secret {
    name  = "acr-admin-password"
    value = data.azurerm_container_registry.main.admin_password
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
    min_replicas = 0
    max_replicas = 1

    container {
      name   = "email-assistant"
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

data "azurerm_resource_group" "main" {
  name = var.shared_resource_group_name
}

data "azurerm_container_registry" "main" {
  name                = var.shared_acr_name
  resource_group_name = data.azurerm_resource_group.main.name
}

data "azurerm_container_app_environment" "main" {
  name                = var.shared_container_app_env_name
  resource_group_name = data.azurerm_resource_group.main.name
}

data "azurerm_log_analytics_workspace" "main" {
  name                = var.shared_log_analytics_workspace_name
  resource_group_name = data.azurerm_resource_group.main.name
}

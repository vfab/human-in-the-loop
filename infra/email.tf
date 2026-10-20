resource "azurerm_email_communication_service" "hitl" {
  name                = "vfab-hitl-email"
  resource_group_name = data.azurerm_resource_group.main.name
  data_location       = "Europe"

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_email_communication_service_domain" "hitl" {
  email_service_name  = azurerm_email_communication_service.hitl.name
  name                = "AzureManagedDomain"
  resource_group_name = data.azurerm_resource_group.main.name
  domain_management   = "AzureManaged"

  lifecycle {
    prevent_destroy = true
  }
}

import {
  to = azurerm_email_communication_service.hitl
  id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${data.azurerm_resource_group.main.name}/providers/Microsoft.Communication/emailServices/vfab-hitl-email"
}

import {
  to = azurerm_email_communication_service_domain.hitl
  id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${data.azurerm_resource_group.main.name}/providers/Microsoft.Communication/emailServices/vfab-hitl-email/domains/AzureManagedDomain"
}

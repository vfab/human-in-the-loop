resource "azurerm_email_communication_service" "hitl" {
  name                = "vfab-hitl-email"
  resource_group_name = data.azurerm_resource_group.main.name
  data_location       = "Europe"

  lifecycle {
    prevent_destroy = true
  }
}

# Note: Email domain management is handled via the Communication Service resource in newer azurerm versions.
# Domain verification and setup may need to be done via Azure Portal or ARM templates.
# See: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/email_communication_service

import {
  to = azurerm_email_communication_service.hitl
  id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${data.azurerm_resource_group.main.name}/providers/Microsoft.Communication/emailServices/vfab-hitl-email"
}

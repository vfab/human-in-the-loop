output "resource_group_name" {
  value       = azurerm_resource_group.this.name
  description = "Resource group hosting the Container Apps deployment."
}

output "container_app_name" {
  value       = azurerm_container_app.this.name
  description = "Azure Container App name."
}

output "container_app_url" {
  value       = "https://${azurerm_container_app.this.latest_revision_fqdn}"
  description = "Public HTTPS URL for the deployed API."
}

output "acr_login_server" {
  value       = azurerm_container_registry.this.login_server
  description = "ACR login server used for pushing container images."
}

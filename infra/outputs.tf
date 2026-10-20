output "container_app_name" {
  value       = azurerm_container_app.this.name
  description = "Azure Container App name."
}

output "container_app_url" {
  value       = "https://${azurerm_container_app.this.latest_revision_fqdn}"
  description = "Public HTTPS URL for the deployed API."
}

output "acr_login_server" {
  value       = data.azurerm_container_registry.main.login_server
  description = "ACR login server used for pushing container images."
}

output "email_service_name" {
  value       = azurerm_email_communication_service.hitl.name
  description = "Email Communication Service name."
}

output "email_service_id" {
  value       = azurerm_email_communication_service.hitl.id
  description = "Email Communication Service ID."
}

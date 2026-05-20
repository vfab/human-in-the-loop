
output "backend_url" {
  value       = "https://${azurerm_container_app.backend.latest_revision_fqdn}"
  description = "FQDN for the backend Container App."
}

output "frontend_url" {
  value       = "https://${azurerm_static_web_app.frontend.default_host_name}"
  description = "Default host name for the Static Web App frontend."
}

output "acr_login_server" {
  value       = data.azurerm_container_registry.target.login_server
  description = "ACR login server used for backend image pushes."
}

output "acs_connection_string" {
  value       = azurerm_communication_service.acs.primary_connection_string
  description = "Primary connection string for Azure Communication Services."
  sensitive   = true
}

output "acs_sender_address" {
  value       = var.acs_email_sender_address
  description = "Configured sender address used by the backend app."
}

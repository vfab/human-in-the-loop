
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

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "westeurope"
}

variable "resource_group_name" {
  description = "The name of the resource group to deploy into."
  type        = string
  default     = "rg-vfab"
}

variable "name_prefix" {
  description = "Deprecated compatibility variable retained for existing tfvars files."
  type        = string
  default     = ""
}

variable "shared_remote_state_enabled" {
  description = "When true, resolve shared foundation resource names from the shared stack Terraform state outputs."
  type        = bool
  default     = false
}

variable "shared_remote_state_path" {
  description = "Path to the shared stack local Terraform state file used when shared_remote_state_enabled is true."
  type        = string
  default     = "/home/vfabro/src/rg-vfab-terraform/shared/terraform.tfstate"
}

variable "acr_name" {
  description = "Name of the Azure Container Registry."
  type        = string
  default     = "ca81b3cb0669acr"
}

variable "container_env_name" {
  description = "Name of the Container Apps Environment."
  type        = string
  default     = "vfab-container-env"
}

variable "frontend_location" {
  description = "Location for Static Web App."
  type        = string
  default     = "westeurope"
}

variable "backend_name" {
  description = "Name of the Container App for backend API."
  type        = string
  default     = "vfab-hitl-backend"
}

variable "frontend_name" {
  description = "Name of the Static Web App for frontend UI."
  type        = string
  default     = "vfab-hitl-frontend"
}

variable "app_config_name" {
  description = "Name of the Azure App Configuration store."
  type        = string
  default     = "vfab-hitl-appconfig"
}

variable "container_image" {
  description = "Container image to deploy to Azure Container Apps."
  type        = string
}

variable "container_cpu" {
  description = "vCPU allocation for the container app revision."
  type        = number
  default     = 0.5
}

variable "container_memory" {
  description = "Memory allocation for the container app revision."
  type        = string
  default     = "1Gi"
}

variable "azure_openai_endpoint" {
  description = "Legacy Azure OpenAI endpoint URL. Deprecated in favor of foundry_openai_endpoint."
  type        = string
  default     = null
  nullable    = true
}

variable "azure_openai_chat_model" {
  description = "Legacy Azure OpenAI deployment name used by the app. Deprecated in favor of foundry_openai_deployment."
  type        = string
  default     = null
  nullable    = true
}

variable "azure_openai_api_version" {
  description = "Legacy Azure OpenAI API version. Deprecated in favor of foundry_openai_api_version."
  type        = string
  default     = null
  nullable    = true
}

variable "azure_openai_api_key" {
  description = "Legacy Azure OpenAI API key. Deprecated in favor of foundry_openai_api_key."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "foundry_openai_endpoint" {
  description = "Microsoft Foundry OpenAI-compatible endpoint URL (for example: https://<resource>.openai.azure.com/)."
  type        = string
  default     = null
  nullable    = true
}

variable "foundry_openai_deployment" {
  description = "Microsoft Foundry model deployment name used by the app."
  type        = string
  default     = null
  nullable    = true
}

variable "foundry_openai_api_version" {
  description = "Microsoft Foundry API version used by the app."
  type        = string
  default     = null
  nullable    = true
}

variable "foundry_openai_api_key" {
  description = "Microsoft Foundry API key."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "key_vault_name" {
  description = "Optional Key Vault name used to source model API keys. When set, openai_api_key_secret_name is read from this vault."
  type        = string
  default     = null
  nullable    = true
}

variable "openai_api_key_secret_name" {
  description = "Secret name in Key Vault containing the Foundry/OpenAI API key."
  type        = string
  default     = "azure-openai-api-key"
}

variable "acs_name" {
  description = "Name of the Azure Communication Services resource."
  type        = string
  default     = "vfab-hitl-acs"
}

variable "acs_email_service_name" {
  description = "Name of the Azure Communication Email service resource."
  type        = string
  default     = "vfab-hitl-email"
}

variable "acs_email_sender_address" {
  description = "Sender address configured in Azure Communication Services Email domain (for example: DoNotReply@<domain>)."
  type        = string
}

variable "acs_data_location" {
  description = "Data location for ACS resources (for example: Europe, United States)."
  type        = string
  default     = "Europe"
}

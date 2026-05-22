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
  description = "Azure OpenAI endpoint URL."
  type        = string
}

variable "azure_openai_chat_model" {
  description = "Azure OpenAI deployment name used by the app."
  type        = string
}

variable "azure_openai_api_version" {
  description = "Azure OpenAI API version."
  type        = string
  default     = "2024-12-01-preview"
}

variable "azure_openai_api_key" {
  description = "Azure OpenAI API key."
  type        = string
  sensitive   = true
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

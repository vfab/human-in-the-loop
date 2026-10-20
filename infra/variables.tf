variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
}

variable "shared_resource_group_name" {
  description = "Shared resource group name."
  type        = string
  default     = "rg-vfab"
}

variable "shared_acr_name" {
  description = "Shared Azure Container Registry name."
  type        = string
  default     = "acrba1e5722"
}

variable "shared_container_app_env_name" {
  description = "Shared Container Apps Environment name."
  type        = string
  default     = "vfab-cae"
}

variable "shared_log_analytics_workspace_name" {
  description = "Shared Log Analytics Workspace name."
  type        = string
  default     = "vfab-log-analytics"
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

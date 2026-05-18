variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Resource group name for Container Apps deployment."
  type        = string
  default     = "rg-hitl-aca"
}

variable "name_prefix" {
  description = "Prefix used in Azure resource names."
  type        = string
  default     = "hitl"
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

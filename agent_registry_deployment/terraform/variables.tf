variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID where Agent Registry and Reasoning Engines will be deployed."
}

variable "region" {
  type        = string
  description = "The Google Cloud region for Vertex AI Agent Registry and resources."
  default     = "us-central1"
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g., dev, staging, prod)."
  default     = "prod"
}

variable "staging_bucket_name" {
  type        = string
  description = "The GCS bucket name used for staging Vertex AI Reasoning Engine packages."
  default     = ""
}

variable "agent_service_account_id" {
  type        = string
  description = "The service account ID for executing registered Reasoning Engines."
  default     = "hr-agent-runner"
}

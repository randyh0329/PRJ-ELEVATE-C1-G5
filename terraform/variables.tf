variable "project_id" {
  description = "The GCP Project ID where resources will be provisioned."
  type        = string
  default     = "pe-group5"
}

variable "region" {
  description = "The primary Google Cloud deployment region (per SDD §7.6 Phase 1 Fast-Path)."
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "The name of the Cloud Run application service."
  type        = string
  default     = "hr-agentic-service"
}

variable "artifact_repo_id" {
  description = "Artifact Registry Docker repository ID."
  type        = string
  default     = "hr-agentic-repo"
}

variable "saas_mcp_base_url" {
  description = "Base URL of the live FastMCP SaaS endpoints."
  type        = string
  default     = "https://mock-saas.aishprabhat.demo.altostrat.com"
}

variable "saas_mcp_token" {
  description = "Personal Access Token for FastMCP authentication (X-MCP-Token)."
  type        = string
  sensitive   = true
  default     = "mcp_HiIwlFkRL-DrjYgdQvO-fMHg8Q8A_YskI5J00qrP8SA"
}

variable "github_repository" {
  description = "GitHub repository path (owner/repo) for Workload Identity Federation OIDC mapping."
  type        = string
  default     = "randyh0329/PRJ-ELEVATE-C1-G5"
}

variable "container_image" {
  description = "Initial container image for Cloud Run bootstrap (defaults to Google Cloud Run hello sample until CI/CD builds the app image)."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "invoker_user" {
  description = "User or group account granted Cloud Run invoker permission (must belong to permitted customer domain)."
  type        = string
  default     = "user:romij@google.com"
}

variable "initial_mcp_user_tokens" {
  description = "Initial JSON mapping of user emails to FastMCP tokens in Secret Manager."
  type        = string
  sensitive   = true
  default     = "{\"romij@google.com\": \"mcp_3DpwwQTaG6eV5SJpTA-QIV7aUqDblj-Qkn8bDkeiHWk\", \"teammate@google.com\": \"mcp_3DpwwQTaG6eV5SJpTA-QIV7aUqDblj-Qkn8bDkeiHWk\"}"
}




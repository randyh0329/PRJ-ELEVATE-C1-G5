variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
  default     = "prj-elevate-c1-g5"
}

variable "primary_region" {
  description = "Primary Cloud Region"
  type        = string
  default     = "us-central1"
}

variable "secondary_region" {
  description = "Secondary Cloud Region for Multi-Region Resiliency"
  type        = string
  default     = "us-east4"
}

variable "environment" {
  description = "Deployment Environment (development | staging | production)"
  type        = string
  default     = "production"
}

variable "container_image_tag" {
  description = "Docker image tag for Cloud Run deployment"
  type        = string
  default     = "1.4.0"
}

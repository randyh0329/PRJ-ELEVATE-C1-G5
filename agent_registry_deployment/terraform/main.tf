terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# 1. Enable Essential Google Cloud APIs
locals {
  required_services = [
    "aiplatform.googleapis.com",
    "discoveryengine.googleapis.com",
    "dlp.googleapis.com",
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "cloudbuild.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ]
  bucket_name = var.staging_bucket_name != "" ? var.staging_bucket_name : "${var.project_id}-agent-registry-staging-${var.environment}"
}

resource "google_project_service" "enabled_apis" {
  for_each                   = toset(local.required_services)
  project                    = var.project_id
  service                    = each.key
  disable_dependent_services = false
  disable_on_destroy         = false
}

# 2. Cloud Storage Staging Bucket for Agent Packages
resource "google_storage_bucket" "agent_staging_bucket" {
  name                        = local.bucket_name
  location                    = var.region
  project                     = var.project_id
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 60
    }
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    workload    = "agent-registry"
  }

  depends_on = [google_project_service.enabled_apis]
}

# 3. Dedicated Service Account for Agent Execution
resource "google_service_account" "agent_runner_sa" {
  account_id   = var.agent_service_account_id
  display_name = "HR Agent Registry Runner Identity"
  description  = "Dedicated IAM identity for running Vertex AI Reasoning Engines and Sub-Agents."
  project      = var.project_id

  depends_on = [google_project_service.enabled_apis]
}

# 4. Scoped Least-Privilege IAM Role Bindings
locals {
  agent_roles = [
    "roles/aiplatform.user",
    "roles/discoveryengine.editor",
    "roles/pubsub.publisher",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]
}

resource "google_project_iam_member" "agent_runner_permissions" {
  for_each = toset(local.agent_roles)
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.agent_runner_sa.email}"
}

# Staging bucket object admin permission for the runner SA
resource "google_storage_bucket_iam_member" "staging_bucket_access" {
  bucket = google_storage_bucket.agent_staging_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.agent_runner_sa.email}"
}

# 5. Enterprise Pub/Sub Event Topics for Async Orchestration
locals {
  pubsub_topics = [
    "hr.lifecycle.transition",
    "hr.approval.requested",
    "hr.approval.completed",
    "hr.case.created",
  ]
}

resource "google_pubsub_topic" "agent_event_topics" {
  for_each = toset(local.pubsub_topics)
  name     = each.key
  project  = var.project_id

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }

  depends_on = [google_project_service.enabled_apis]
}

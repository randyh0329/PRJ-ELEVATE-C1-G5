terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.10.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# -----------------------------------------------------------------------------
# 1. Enable Required Google Cloud APIs
# -----------------------------------------------------------------------------
locals {
  services = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "orgpolicy.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "agentregistry.googleapis.com"
  ]
}

resource "google_project_service" "enabled_apis" {
  for_each                   = toset(local.services)
  project                    = var.project_id
  service                    = each.key
  disable_on_destroy         = false
  disable_dependent_services = false
}

# -----------------------------------------------------------------------------
# 2. Artifact Registry Docker Repository

# -----------------------------------------------------------------------------
resource "google_artifact_registry_repository" "docker_repo" {
  depends_on    = [google_project_service.enabled_apis]
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repo_id
  description   = "Docker container registry for Enterprise HR Agentic Solution (MVP 1)"
  format        = "DOCKER"
}

# -----------------------------------------------------------------------------
# 3. Secret Manager (SaaS FastMCP Token - SDD §4.1 & §7.2)
# -----------------------------------------------------------------------------
resource "google_secret_manager_secret" "saas_mcp_token" {
  depends_on = [google_project_service.enabled_apis]
  project    = var.project_id
  secret_id  = "saas-mcp-token"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "saas_mcp_token_version" {
  secret      = google_secret_manager_secret.saas_mcp_token.id
  secret_data = var.saas_mcp_token
}

# User-level FastMCP Token Mapping (JSON Map: email -> token)
resource "google_secret_manager_secret" "mcp_user_tokens" {
  depends_on = [google_project_service.enabled_apis]
  project    = var.project_id
  secret_id  = "mcp-user-tokens"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "mcp_user_tokens_initial" {
  secret      = google_secret_manager_secret.mcp_user_tokens.id
  secret_data = var.initial_mcp_user_tokens
}

# -----------------------------------------------------------------------------
# 4. Service Account for Cloud Run Runtime (Least Privilege - SDD §7.2)
# -----------------------------------------------------------------------------
resource "google_service_account" "cloud_run_sa" {
  depends_on   = [google_project_service.enabled_apis]
  project      = var.project_id
  account_id   = "hr-agent-runner-sa"
  display_name = "Cloud Run Service Account for HR Agentic Solution"
}

# Grant Cloud Run SA read access to Secret Manager token
resource "google_secret_manager_secret_iam_member" "token_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.saas_mcp_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# Grant Cloud Run SA read & write access to user token mapping in Secret Manager
resource "google_secret_manager_secret_iam_member" "user_tokens_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.mcp_user_tokens.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "user_tokens_version_adder" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.mcp_user_tokens.secret_id
  role      = "roles/secretmanager.secretVersionAdder"
  member    = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}


# Grant Cloud Run SA logging and monitoring writer roles
resource "google_project_iam_member" "cloud_run_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_project_iam_member" "cloud_run_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# -----------------------------------------------------------------------------
# 5. Workload Identity Federation (WIF) for GitHub Actions CI/CD (SDD §7.1)
# -----------------------------------------------------------------------------
resource "google_iam_workload_identity_pool" "github_pool" {
  depends_on                = [google_project_service.enabled_apis]
  project                   = var.project_id
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions WIF Pool"
  description               = "Identity pool for GitHub Actions automated CI/CD pipeline"
}

resource "google_iam_workload_identity_pool_provider" "github_provider" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions-provider"
  display_name                       = "GitHub Actions OIDC Provider"
  description                        = "OIDC identity provider for randyh0329 GitHub repositories"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
  }

  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Service Account dedicated for GitHub Actions deployment
resource "google_service_account" "github_deployer_sa" {
  depends_on   = [google_project_service.enabled_apis]
  project      = var.project_id
  account_id   = "github-deployer-sa"
  display_name = "GitHub Actions CI/CD Deployer Service Account"
}

# Allow GitHub Actions to impersonate this deployer service account via WIF
resource "google_service_account_iam_member" "github_wif_impersonation" {
  service_account_id = google_service_account.github_deployer_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.github_repository}"
}

# Grant deployer SA permissions to push images and deploy to Cloud Run
resource "google_project_iam_member" "deployer_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_deployer_sa.email}"
}

resource "google_project_iam_member" "deployer_cloud_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.github_deployer_sa.email}"
}

resource "google_service_account_iam_member" "deployer_sa_user" {
  service_account_id = google_service_account.cloud_run_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer_sa.email}"
}

# -----------------------------------------------------------------------------
# 6. Cloud Run Service (SDD §7.6 Phase 1 Fast-Path MVP)
# -----------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "hr_agentic_service" {
  depends_on = [
    google_project_service.enabled_apis,
    google_artifact_registry_repository.docker_repo,
    google_secret_manager_secret_version.saas_mcp_token_version,
    google_secret_manager_secret_iam_member.token_accessor
  ]

  project  = var.project_id
  location = var.region
  name     = var.service_name
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloud_run_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = var.container_image

      resources {

        limits = {
          cpu    = "1000m"
          memory = "1024Mi"
        }
      }

      ports {
        container_port = 8080
      }

      env {
        name = "SAAS_MCP_BASE_URL"

        value = var.saas_mcp_base_url
      }

      env {
        name  = "USE_LIVE_MCP"
        value = "true"
      }

      env {
        name  = "DEFAULT_CALLER_ID"
        value = "EMP-509"
      }

      env {
        name = "SAAS_MCP_CREDENTIAL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.saas_mcp_token.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "MCP_USER_TOKENS_SECRET_ID"
        value = google_secret_manager_secret.mcp_user_tokens.secret_id
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }


      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        timeout_seconds   = 3
        period_seconds    = 15
        failure_threshold = 3
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }
}

# Grant GitHub Actions CI/CD deployer service account invoke permission
resource "google_cloud_run_v2_service_iam_member" "deployer_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.hr_agentic_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.github_deployer_sa.email}"
}

# Allow public invocations (allUsers) on Cloud Run
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.hr_agentic_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# -----------------------------------------------------------------------------
# 7. Dedicated Microservice: Policy RAG A2A Agent (Service 2 - Private)
# -----------------------------------------------------------------------------
resource "google_service_account" "policy_rag_sa" {
  depends_on   = [google_project_service.enabled_apis]
  project      = var.project_id
  account_id   = "policy-rag-sa"
  display_name = "Policy RAG A2A Agent Service Account"
}

resource "google_cloud_run_v2_service" "hr_policy_rag_service" {
  depends_on = [
    google_project_service.enabled_apis,
    google_artifact_registry_repository.docker_repo
  ]

  project  = var.project_id
  location = var.region
  name     = "hr-policy-rag-service"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.policy_rag_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "2000m"
          memory = "2048Mi"
        }
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        timeout_seconds   = 3
        period_seconds    = 15
        failure_threshold = 3
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }
}

# Grant Orchestrator SA permission to invoke Policy RAG (IAM OIDC Authentication)
resource "google_cloud_run_v2_service_iam_member" "orchestrator_invokes_policy_rag" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.hr_policy_rag_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# Grant CI/CD deployer SA permissions
resource "google_cloud_run_v2_service_iam_member" "deployer_invokes_policy_rag" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.hr_policy_rag_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.github_deployer_sa.email}"
}

resource "google_service_account_iam_member" "deployer_sa_user_policy_rag" {
  service_account_id = google_service_account.policy_rag_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer_sa.email}"
}


# -----------------------------------------------------------------------------
# 8. Dedicated Microservice: SaaS Integration Adapters (Service 3 - Private)
# -----------------------------------------------------------------------------
resource "google_service_account" "saas_adapter_sa" {
  depends_on   = [google_project_service.enabled_apis]
  project      = var.project_id
  account_id   = "saas-adapter-sa"
  display_name = "SaaS FastMCP Adapters Service Account"
}

resource "google_secret_manager_secret_iam_member" "adapter_token_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.saas_mcp_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.saas_adapter_sa.email}"
}

resource "google_cloud_run_v2_service" "saas_adapter_service" {
  depends_on = [
    google_project_service.enabled_apis,
    google_artifact_registry_repository.docker_repo,
    google_secret_manager_secret_version.saas_mcp_token_version,
    google_secret_manager_secret_iam_member.adapter_token_accessor
  ]

  project  = var.project_id
  location = var.region
  name     = "saas-integration-adapters"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.saas_adapter_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "1000m"
          memory = "1024Mi"
        }
      }

      ports {
        container_port = 8080
      }

      env {
        name = "SAAS_MCP_CREDENTIAL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.saas_mcp_token.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        timeout_seconds   = 3
        period_seconds    = 15
        failure_threshold = 3
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }
}

# Grant Orchestrator SA permission to invoke SaaS Adapters (IAM OIDC Authentication)
resource "google_cloud_run_v2_service_iam_member" "orchestrator_invokes_saas_adapter" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.saas_adapter_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# Grant CI/CD deployer SA permissions
resource "google_cloud_run_v2_service_iam_member" "deployer_invokes_saas_adapter" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.saas_adapter_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.github_deployer_sa.email}"
}

resource "google_service_account_iam_member" "deployer_sa_user_saas_adapter" {
  service_account_id = google_service_account.saas_adapter_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer_sa.email}"
}






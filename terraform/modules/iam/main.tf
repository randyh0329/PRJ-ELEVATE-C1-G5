# Least Privilege IAM Service Accounts & Role Bindings (SDD §4.9)

resource "google_service_account" "gateway" {
  account_id   = "sa-gateway"
  display_name = "API Gateway Cloud Run Service Account"
  project      = var.project_id
}

resource "google_service_account" "orchestrator" {
  account_id   = "sa-orchestrator"
  display_name = "Agent Orchestrator Service Account"
  project      = var.project_id
}

resource "google_service_account" "ww_adapter" {
  account_id   = "sa-ww-adapter"
  display_name = "WorkWeek HCM Adapter Service Account"
  project      = var.project_id
}

resource "google_service_account" "si_adapter" {
  account_id   = "sa-si-adapter"
  display_name = "ServiceImmediately ITSM Adapter Service Account"
  project      = var.project_id
}

resource "google_service_account" "telemetry" {
  account_id   = "sa-telemetry"
  display_name = "Structured Telemetry Logger Service Account"
  project      = var.project_id
}

# Gateway Permissions: Model Armor, DLP user, Run invoker
resource "google_project_iam_member" "gateway_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.gateway.email}"
}

# Orchestrator Permissions: Vertex AI User, Token Creator
resource "google_project_iam_member" "orchestrator_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

resource "google_project_iam_member" "orchestrator_datastore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Adapters Permissions: Secret Manager & Cloud Tasks Enqueuer
resource "google_project_iam_member" "ww_tasks" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.ww_adapter.email}"
}

resource "google_project_iam_member" "si_tasks" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.si_adapter.email}"
}

output "gateway_sa_email" { value = google_service_account.gateway.email }
output "orchestrator_sa_email" { value = google_service_account.orchestrator.email }
output "ww_adapter_sa_email" { value = google_service_account.ww_adapter.email }
output "si_adapter_sa_email" { value = google_service_account.si_adapter.email }

output "cloud_run_uri" {
  description = "The public HTTPS endpoint URI of the deployed Cloud Run service."
  value       = google_cloud_run_v2_service.hr_agentic_service.uri
}

output "artifact_registry_repository_url" {
  description = "Docker image repository URL in Artifact Registry."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo_id}"
}

output "workload_identity_provider" {
  description = "Workload Identity Provider resource name for GitHub Actions auth."
  value       = google_iam_workload_identity_pool_provider.github_provider.name
}

output "github_deployer_service_account" {
  description = "Service Account email used by GitHub Actions CI/CD to authenticate."
  value       = google_service_account.github_deployer_sa.email
}

output "cloud_run_runtime_service_account" {
  description = "Service Account email executing the Cloud Run container runtime."
  value       = google_service_account.cloud_run_sa.email
}

output "policy_rag_uri" {
  description = "The internal HTTPS endpoint URI of the Policy RAG Cloud Run service."
  value       = google_cloud_run_v2_service.hr_policy_rag_service.uri
}

output "saas_adapter_uri" {
  description = "The internal HTTPS endpoint URI of the SaaS FastMCP Adapters Cloud Run service."
  value       = google_cloud_run_v2_service.saas_adapter_service.uri
}

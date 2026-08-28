output "project_id" {
  description = "The Google Cloud Project ID."
  value       = var.project_id
}

output "region" {
  description = "The Google Cloud Region."
  value       = var.region
}

output "staging_bucket_uri" {
  description = "The GCS URI of the staging bucket for Reasoning Engine artifacts."
  value       = "gs://${google_storage_bucket.agent_staging_bucket.name}"
}

output "service_account_email" {
  description = "The email address of the HR Agent Runner Service Account."
  value       = google_service_account.agent_runner_sa.email
}

output "created_pubsub_topics" {
  description = "List of created Pub/Sub topics for asynchronous agent lifecycle events."
  value       = [for topic in google_pubsub_topic.agent_event_topics : topic.id]
}

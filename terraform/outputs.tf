output "api_gateway_url" {
  description = "Production API Gateway URL"
  value       = module.cloud_run.gateway_url
}

output "mock_backends_url" {
  description = "Production Mock Backends URL"
  value       = module.cloud_run.mocks_url
}

output "dlp_template_name" {
  description = "Primary DLP De-identification Template Resource Name"
  value       = module.dlp.primary_dlp_template_name
}

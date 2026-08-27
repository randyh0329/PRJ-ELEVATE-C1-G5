# Cloud Run v2 Services (SDD §3.1)

resource "google_cloud_run_v2_service" "gateway" {
  name     = "elevate-api-gateway"
  location = var.primary_region
  project  = var.project_id

  template {
    service_account = var.gateway_sa_email

    containers {
      image = "gcr.io/${var.project_id}/elevate-gateway:${var.container_image_tag}"
      ports {
        container_port = 8000
      }
      resources {
        limits = {
          cpu    = "2000m"
          memory = "2Gi"
        }
        cpu_idle = true
        startup_cpu_boost = true
      }
    }
  }
}

resource "google_cloud_run_v2_service" "mocks" {
  name     = "elevate-mock-backends"
  location = var.primary_region
  project  = var.project_id

  template {
    service_account = var.ww_adapter_sa_email

    containers {
      image = "gcr.io/${var.project_id}/elevate-mocks:${var.container_image_tag}"
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "1000m"
          memory = "1Gi"
        }
      }
    }
  }
}

output "gateway_url" { value = google_cloud_run_v2_service.gateway.uri }
output "mocks_url" { value = google_cloud_run_v2_service.mocks.uri }

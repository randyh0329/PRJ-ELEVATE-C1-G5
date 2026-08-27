# Cloud Tasks Queues with Exponential Backoff (SDD §5.2)

resource "google_cloud_tasks_queue" "ww_queue" {
  name     = "workweek-mutating-queue"
  location = var.primary_region
  project  = var.project_id

  rate_limits {
    max_dispatches_per_second = 50
    max_concurrent_dispatches = 20
  }

  retry_config {
    max_attempts       = 5
    min_backoff        = "0.500s"
    max_backoff        = "8.000s"
    max_doublings      = 4
    max_retry_duration = "1800s" # 30-minute staleness bound
  }
}

resource "google_cloud_tasks_queue" "si_queue" {
  name     = "serviceimmediately-mutating-queue"
  location = var.primary_region
  project  = var.project_id

  rate_limits {
    max_dispatches_per_second = 50
    max_concurrent_dispatches = 20
  }

  retry_config {
    max_attempts       = 5
    min_backoff        = "0.500s"
    max_backoff        = "8.000s"
    max_doublings      = 4
    max_retry_duration = "1800s" # 30-minute staleness bound
  }
}

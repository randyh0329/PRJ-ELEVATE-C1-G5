# Firestore Native Database & TTL Policies (SDD §4.6)

resource "google_firestore_database" "database" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.primary_region
  type        = "FIRESTORE_NATIVE"
}

# TTL Policy on sessions (30 days)
resource "google_firestore_field" "session_ttl" {
  project    = var.project_id
  database   = google_firestore_database.database.name
  collection = "sessions"
  field      = "ttl_expiry"

  ttl_config {}
}

# TTL Policy on sagas (30 days)
resource "google_firestore_field" "saga_ttl" {
  project    = var.project_id
  database   = google_firestore_database.database.name
  collection = "sagas"
  field      = "ttl_expiry"

  ttl_config {}
}

# TTL Policy on replay defense token nonces (120 seconds)
resource "google_firestore_field" "token_cache_ttl" {
  project    = var.project_id
  database   = google_firestore_database.database.name
  collection = "token_cache"
  field      = "ttl"

  ttl_config {}
}

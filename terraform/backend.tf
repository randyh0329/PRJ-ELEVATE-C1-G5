terraform {
  backend "gcs" {
    bucket = "pe-group5-tfstate"
    prefix = "hr-agentic/state"
  }
}

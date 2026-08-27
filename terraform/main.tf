terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.primary_region
}

module "iam" {
  source     = "./modules/iam"
  project_id = var.project_id
}

module "dlp" {
  source         = "./modules/dlp"
  project_id     = var.project_id
  primary_region = var.primary_region
}

module "firestore" {
  source         = "./modules/firestore"
  project_id     = var.project_id
  primary_region = var.primary_region
}

module "cloud_tasks" {
  source         = "./modules/cloud_tasks"
  project_id     = var.project_id
  primary_region = var.primary_region
}

module "cloud_run" {
  source              = "./modules/cloud_run"
  project_id          = var.project_id
  primary_region      = var.primary_region
  container_image_tag = var.container_image_tag
  gateway_sa_email    = module.iam.gateway_sa_email
  ww_adapter_sa_email = module.iam.ww_adapter_sa_email
}

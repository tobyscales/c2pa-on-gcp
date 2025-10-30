# main.tf

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "google_project_service" "apis" {
  for_each = toset([
    "storage.googleapis.com",
    "cloudkms.googleapis.com",
    "privateca.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com"
  ])
  project = var.project_id
  service = each.key
}

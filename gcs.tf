# gcs.tf

resource "google_storage_bucket" "uploads" {
  name          = "c2pa-uploads-${random_id.suffix.hex}"
  location      = var.location
  force_destroy = true
  project       = var.project_id
}

resource "google_storage_bucket" "signed" {
  name          = "c2pa-signed-${random_id.suffix.hex}"
  location      = var.location
  force_destroy = true
  project       = var.project_id
}

# backend.tf

# This bucket will store the Terraform state file remotely.
# It enables collaboration and state locking.
resource "google_storage_bucket" "tfstate" {
  name          = "${var.project_id}-tfstate" # Bucket names must be globally unique
  location      = var.multi_region_location
  project       = var.project_id
  force_destroy = false # Protect this bucket from accidental deletion

  # Enable versioning to keep a history of state files, allowing for recovery.
  versioning {
    enabled = true
  }

  # Prevent accidental deletion of the state bucket.
  # To delete this bucket, you must first set this to 'false'.
  lifecycle {
    prevent_destroy = true
  }
}

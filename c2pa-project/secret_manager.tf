# secret_manager.tf

# Create a secret to hold the author name
resource "google_secret_manager_secret" "author_name_secret" {
  project   = var.project_id
  secret_id = "c2pa-author-name"

  replication {
    auto {}
  }
  depends_on = [
    google_project_service.apis["secretmanager.googleapis.com"]
  ]

}

# Add the secret value as a new version
resource "google_secret_manager_secret_version" "author_name_version" {
  secret      = google_secret_manager_secret.author_name_secret.id
  secret_data = var.c2pa_author_name
}

# Create a secret to hold the claim generator string
resource "google_secret_manager_secret" "claim_generator_secret" {
  project   = var.project_id
  secret_id = "c2pa-claim-generator"

  replication {
    auto {}
  }
}

# Add the secret value as a new version
resource "google_secret_manager_secret_version" "claim_generator_version" {
  secret      = google_secret_manager_secret.claim_generator_secret.id
  secret_data = var.c2pa_claim_generator
}

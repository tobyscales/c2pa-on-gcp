# cloud_function.tf

# 1. Create a Pub/Sub topic to receive GCS notifications
resource "google_pubsub_topic" "gcs_events" {
  name    = "gcs-c2pa-uploads"
  project = var.project_id
}

# 2. Configure GCS to send a notification to the topic on object creation
resource "google_storage_notification" "gcs_notification" {
  bucket         = google_storage_bucket.uploads.name
  topic          = google_pubsub_topic.gcs_events.id
  payload_format = "JSON_API_V1"
  event_types    = ["OBJECT_FINALIZE"]
}

# 3. Define the service account for the functions
resource "google_service_account" "function_sa" {
  account_id   = "c2pa-signer-sa"
  display_name = "C2PA Signer Service Account"
  project      = var.project_id
}

# 4. Grant the service account permissions, including Secret Accessor
resource "google_project_iam_member" "function_permissions" {
  for_each = toset([
    "roles/cloudkms.signerVerifier",
    "roles/privateca.certificateRequester",
    "roles/storage.objectAdmin",
    "roles/secretmanager.secretAccessor" # <--- ADD THIS ROLE
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.function_sa.email}"
}

# 5. Package the function source code
data "archive_file" "source" {
  type        = "zip"
  source_dir  = "${path.module}/function_source"
  output_path = "/tmp/function-source.zip"
}

resource "google_storage_bucket_object" "function_archive" {
  name   = "source.zip"
  bucket = google_storage_bucket.uploads.name
  source = data.archive_file.source.output_path
}

# 6. Deploy one function to each specified region
resource "google_cloudfunctions_function" "c2pa_signer" {
  for_each = toset(var.regions)

  name                  = "c2pa-signer-function-${each.key}"
  # ... (other function settings) ...
  service_account_email = google_service_account.function_sa.email
  
  pubsub_trigger {
    topic = google_pubsub_topic.gcs_events.name
  }

  # Pass the SECRET NAMES (not values) as environment variables
  environment_variables = {
    PROJECT_ID                  = var.project_id # Pass project_id for secret path
    SIGNED_BUCKET_NAME          = google_storage_bucket.signed.name
    KMS_KEY_ID                  = google_kms_crypto_key.signing_key.id
    CA_POOL_ID                  = google_privateca_ca_pool.pool.id
    AUTHOR_NAME_SECRET_ID       = google_secret_manager_secret.author_name_secret.secret_id
    CLAIM_GENERATOR_SECRET_ID   = google_secret_manager_secret.claim_generator_secret.secret_id
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.function_permissions,
    google_storage_notification.gcs_notification
  ]
}

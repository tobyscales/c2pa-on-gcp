# cloud_function.tf


# First, get the special Google-managed service account for the GCS service.
data "google_storage_project_service_account" "gcs_account" {
  project = var.project_id
}

# Second, grant that service account the permission to publish to our specific topic.
resource "google_pubsub_topic_iam_member" "gcs_pubsub_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.gcs_events.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"
}

# This depends_on ensures that the IAM binding is created before Terraform tries
# to create the notification, which requires the permission.


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

# 6. Deploy one function to each specified region using Cloud Functions 2nd Gen
resource "google_cloudfunctions2_function" "c2pa_signer" {
  for_each = toset(var.regions)

  name     = "c2pa-signer-function-${each.key}"
  location = each.key # 2nd Gen uses "location"

  # Build configuration specifies the source and runtime
  build_config {
    runtime     = "python310"
    entry_point = "c2pa_sign_pubsub"
    source {
      storage_source {
        bucket = google_storage_bucket.uploads.name
        object = google_storage_bucket_object.function_archive.name
      }
    }
  }

  # Service configuration specifies runtime behavior, networking, and environment
  service_config {
    # Set a higher timeout if your signing process could take longer
    timeout_seconds       = 60 
    service_account_email = google_service_account.function_sa.email

    # Environment variables are nested here
    environment_variables = {
      # Pass the project ID for Secret Manager client
      PROJECT_ID                  = var.project_id 
      SIGNED_BUCKET_NAME          = google_storage_bucket.signed.name
      KMS_KEY_ID                  = google_kms_crypto_key.signing_key.id
      CA_POOL_ID                  = google_privateca_ca_pool.pool.id
      AUTHOR_NAME_SECRET_ID       = google_secret_manager_secret.author_name_secret.secret_id
      CLAIM_GENERATOR_SECRET_ID   = google_secret_manager_secret.claim_generator_secret.secret_id
    }
  }

  # Event trigger for Pub/Sub events
  event_trigger {
    trigger_region = each.key
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.gcs_events.id
    retry_policy   = "RETRY_POLICY_RETRY"
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.function_permissions,
    google_storage_notification.gcs_notification
  ]
}

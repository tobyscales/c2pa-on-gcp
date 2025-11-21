# cloud_function.tf

# -----------------------------------------------------------------------------
# 1. Service Accounts & IAM Setup
# -----------------------------------------------------------------------------

# Get the Google-managed service account for GCS (to publish notifications)
data "google_storage_project_service_account" "gcs_account" {
  project = var.project_id
}

# Get project number for constructing default service account emails
#data "google_project" "project" {
#  project_id = var.project_id
#}

# Create the dedicated Service Account for the Function Runtime
resource "google_service_account" "function_sa" {
  account_id   = "c2pa-signer-sa"
  display_name = "C2PA Signer Service Account"
  project      = var.project_id
}

# Grant Runtime Permissions (KMS, Secret Manager, Storage, etc.)
resource "google_project_iam_member" "function_permissions" {
  for_each = toset([
    "roles/cloudkms.signerVerifier",
    "roles/privateca.certificateManager",
    "roles/storage.objectAdmin",
    "roles/secretmanager.secretAccessor",
    "roles/artifactregistry.reader",
    "roles/logging.logWriter",
    "roles/eventarc.eventReceiver",
    "roles/run.invoker" 
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.function_sa.email}"
}

# -----------------------------------------------------------------------------
# 2. Build System Permissions
# -----------------------------------------------------------------------------

# NOTE: Gen 2 uses Cloud Build. We grant the default Compute Service Account 
# (often used by Cloud Build) access to read the source code bucket.
resource "google_storage_bucket_iam_member" "build_source_reader" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "cloud_build_permissions" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.builder"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}


# -----------------------------------------------------------------------------
# 3. Function Source & Deployment (Gen 2)
# -----------------------------------------------------------------------------

data "archive_file" "source" {
  type        = "zip"
  source_dir  = "${path.module}/function_source"
  output_path = "/tmp/function-source.zip"
}

resource "google_storage_bucket_object" "function_archive" {
  name   = "source-${data.archive_file.source.output_md5}.zip" # Add hash to force redeploy on change
  bucket = google_storage_bucket.uploads.name
  source = data.archive_file.source.output_path
}

resource "google_cloudfunctions2_function" "c2pa_signer" {
  for_each = toset(var.regions)

  name        = "c2pa-signer-function-${each.key}"
  location    = each.key
  description = "C2PA signing function triggered by GCS uploads via Pub/Sub (Gen 2)."

  build_config {
    runtime     = "python310"
    entry_point = "c2pa_sign_pubsub" # Must match the function name in main.py
    source {
      storage_source {
        bucket = google_storage_bucket.uploads.name
        object = google_storage_bucket_object.function_archive.name
      }
    }
  }

  service_config {
    max_instance_count    = 10
    available_memory      = "512M"
    timeout_seconds       = 60
    service_account_email = google_service_account.function_sa.email
    
    environment_variables = {
      PROJECT_ID                = var.project_id
      SIGNED_BUCKET_NAME        = google_storage_bucket.signed.name
      KMS_KEY_ID                = google_kms_crypto_key.signing_key.id
      CA_POOL_ID                = google_privateca_ca_pool.pool.id
      AUTHOR_NAME_SECRET_ID     = google_secret_manager_secret.author_name_secret.secret_id
      CLAIM_GENERATOR_SECRET_ID = google_secret_manager_secret.claim_generator_secret.secret_id
    }
  }

event_trigger {
    # FIX: Dynamically set the trigger region to match the function deployment region
    trigger_region = each.key 
    
    # This event type fires when a new object is finalized (uploaded)
    event_type     = "google.cloud.storage.object.v1.finalized"
    retry_policy   = "RETRY_POLICY_RETRY"
    
    # Use the function's SA to manage the trigger identity
    service_account_email = google_service_account.function_sa.email
    
    event_filters {
      attribute = "bucket"
      value     = google_storage_bucket.uploads.name
    }
  }

  depends_on = [
    google_project_iam_member.function_permissions
  ]
}

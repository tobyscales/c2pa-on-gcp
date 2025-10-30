# cloud_function.tf

resource "google_service_account" "function_sa" {
  account_id   = "c2pa-signer-sa"
  display_name = "C2PA Signer Service Account"
  project      = var.project_id
}

resource "google_project_iam_member" "function_permissions" {
  for_each = toset([
    "roles/cloudkms.signerVerifier",
    "roles/privateca.certificateRequester",
    "roles/storage.objectAdmin"
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.function_sa.email}"
}

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

resource "google_cloudfunctions_function" "c2pa_signer" {
  name                  = "c2pa-signer-function"
  runtime               = "python310"
  source_archive_bucket = google_storage_bucket.uploads.name
  source_archive_object = google_storage_bucket_object.function_archive.name
  entry_point           = "c2pa_sign"
  service_account_email = google_service_account.function_sa.email
  event_trigger {
    event_type = "google.storage.object.finalize"
    resource   = google_storage_bucket.uploads.name
  }
  environment_variables = {
    SIGNED_BUCKET_NAME = google_storage_bucket.signed.name
    KMS_KEY_ID         = google_kms_crypto_key.signing_key.id
    CA_POOL_ID         = google_privateca_ca_pool.pool.id
  }
  depends_on = [
    google_project_service.apis,
    google_project_iam_member.function_permissions
  ]
}

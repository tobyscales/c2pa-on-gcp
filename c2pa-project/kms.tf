# kms.tf

resource "google_kms_key_ring" "keyring" {
  name     = "c2pa-ring-${random_id.suffix.hex}"
  location = "global"
  project  = var.project_id

    depends_on = [
    google_project_service.apis["cloudkms.googleapis.com"]
  ]
}

resource "google_kms_crypto_key" "signing_key" {
  name            = "c2pa-signing-key"
  key_ring        = google_kms_key_ring.keyring.id
  purpose         = "ASYMMETRIC_SIGN"
  version_template {
    algorithm = "RSA_SIGN_PSS_2048_SHA256"
    protection_level = "HSM"
  }
  destroy_scheduled_duration = "86400s" # 24 hours
}

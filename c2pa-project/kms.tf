# kms.tf

resource "google_kms_key_ring" "keyring" {
  # This line tells Terraform to use the aliased provider for this resource
  provider = google.multi_region_provider

  name     = "c2pa-keyring"
  location = var.multi_region_location # This should be "US", "EU", etc.
  project  = var.project_id
}

resource "google_kms_crypto_key" "signing_key" {
  name            = "c2pa-signing-key"
  key_ring        = google_kms_key_ring.keyring.id
  purpose         = "ASYMMETRIC_SIGN"
  version_template {
    algorithm        = "RSA_SIGN_PKCS1_4096_SHA256"
    protection_level = "HSM"
  }
}

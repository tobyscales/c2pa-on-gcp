# scripts.tf
 
resource "null_resource" "provision_c2pa_cert" {
  for_each = toset(var.regions)

  # Re-run this script only if the KMS Key or CA Pool ID changes
  triggers = {
    kms_key_id = google_kms_crypto_key.signing_key[each.key].id
    ca_pool_id = google_privateca_ca_pool.pool[each.key].id
    script_hash = filesha256("${path.module}/scripts/provision_cert.py")
  }

  provisioner "local-exec" {
    # 'uv run' creates an ephemeral virtualenv, installs deps, runs script, and cleans up.
    # We explicitly request the google clients and cryptography.
    command = <<EOT
      uv run \
      --python 3.11 \
      --with google-cloud-kms \
      --with google-cloud-private-ca \
      --with cryptography \
      python ${path.module}/scripts/provision_cert.py
    EOT

    # Pass the Terraform values into the Python environment
    environment = {
      PROJECT_ID  = var.project_id
      LOCATION    = each.key
      CA_POOL_ID  = google_privateca_ca_pool.pool[each.key].name
      # We append the version '1' here. In a real setup, you might use a data source to find the primary version.
      KMS_KEY_ID  = "${google_kms_crypto_key.signing_key[each.key].id}/cryptoKeyVersions/1"
    }
  }

  # STRICT DEPENDENCY ORDERING
  # The script will fail if the API isn't ready or the user doesn't have permissions yet.
  depends_on = [
    google_privateca_certificate_authority.regional_ca, # Wait for CA to be ready
    google_kms_crypto_key.signing_key,                  # Wait for Key to be ready
    google_kms_crypto_key_iam_member.cas_signer_binding # Wait for permissions
  ]
}
# -----------------------------------------------------------------------------
# 1. Write the Python Script to Disk (With PEP 723 Metadata)
# -----------------------------------------------------------------------------
resource "local_file" "create_cert_script" {
  filename = "${path.module}/create_cert.py"
  content  = <<EOF
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "google-cloud-kms",
#     "google-cloud-private-ca",
#     "protobuf",
# ]
# ///

import argparse
import time
from google.cloud import kms
from google.cloud import privateca_v1
from google.cloud.privateca_v1.types import (
    Certificate, CertificateConfig, PublicKey, SubjectConfig, X509Parameters, KeyUsage
)
from google.protobuf import duration_pb2

def create_c2pa_certificate(project_id, location, pool_id, key_ring, key_name, key_version, common_name):
    client_kms = kms.KeyManagementServiceClient()
    client_ca = privateca_v1.CertificateAuthorityServiceClient()
    
    # Construct full resource names
    ca_pool_full = f"projects/{project_id}/locations/{location}/caPools/{pool_id}"
    kms_key_full = f"projects/{project_id}/locations/{location}/keyRings/{key_ring}/cryptoKeys/{key_name}/cryptoKeyVersions/{key_version}"

    print(f"--- Fetching Public Key from KMS: {key_name} ---")
    try:
        # Retry logic for KMS propagation
        kms_public_key = None
        for _ in range(5):
            try:
                kms_public_key = client_kms.get_public_key(request={"name": kms_key_full})
                break
            except Exception:
                time.sleep(2)
        
        if not kms_public_key:
            raise Exception("Could not fetch public key after retries")

    except Exception as e:
        print(f"Error fetching KMS key: {e}")
        return

    pub_key_obj = PublicKey(
        key=kms_public_key.pem.encode("utf-8"),
        format=PublicKey.KeyFormat.PEM
    )

    print(f"--- Requesting Certificate from Pool: {pool_id} ---")
    
    key_usage = KeyUsage(
        base_key_usage=KeyUsage.KeyUsageOptions(
            digital_signature=True,
            content_commitment=True, 
        )
    )

    config = CertificateConfig(
        public_key=pub_key_obj,
        subject_config=SubjectConfig(
            subject=SubjectConfig.Subject(
                common_name=common_name,
                organization="C2PA Signing Org",
                country_code="US"
            )
        ),
        x509_config=X509Parameters(key_usage=key_usage)
    )

    # Lifetime: 30 Days
    lifetime = duration_pb2.Duration(seconds=30 * 24 * 60 * 60)

    request = privateca_v1.CreateCertificateRequest(
        parent=ca_pool_full,
        certificate_id=f"c2pa-signer-{int(time.time())}", 
        certificate=Certificate(config=config, lifetime=lifetime)
    )

    try:
        response = client_ca.create_certificate(request=request)
        print(f"✅ Certificate Created: {response.name}")
    except Exception as e:
        # If it already exists, we are good. 
        if "already exists" in str(e):
            print(f"ℹ️ Certificate already exists.")
        else:
            raise e

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_id", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--pool_id", required=True)
    parser.add_argument("--key_ring", required=True)
    parser.add_argument("--key_name", required=True)
    parser.add_argument("--key_version", default="1")
    parser.add_argument("--common_name", default="C2PA Signer")
    args = parser.parse_args()

    create_c2pa_certificate(
        args.project_id, args.location, args.pool_id, 
        args.key_ring, args.key_name, args.key_version, args.common_name
    )
EOF
}

# -----------------------------------------------------------------------------
# 2. Execute using UV
# -----------------------------------------------------------------------------
resource "null_resource" "issue_certificate" {
  triggers = {
    key_id  = google_kms_crypto_key.signing_key.id
    pool_id = google_privateca_ca_pool.pool.id
  }

  provisioner "local-exec" {
    # We use /bin/bash to ensure consistent behavior for conditional logic
    interpreter = ["/bin/bash", "-c"]
    
    command = <<EOT
      # 1. Check for uv; download if missing
      if ! command -v uv &> /dev/null; then
        echo "uv not found. Installing from astral.sh..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        
        # Add default install paths to PATH for this session
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
      fi

      echo "Using uv version: $(uv --version)"

      # 2. Run the script
      # 'uv run' reads the dependencies from the Python file header,
      # creates a cached venv, installs deps, and runs the code.
      uv run ${local_file.create_cert_script.filename} \
        --project_id ${var.project_id} \
        --location ${google_privateca_ca_pool.pool.location} \
        --pool_id ${google_privateca_ca_pool.pool.name} \
        --key_ring ${google_kms_key_ring.key_ring.name} \
        --key_name ${google_kms_crypto_key.signing_key.name} \
        --key_version "1"
    EOT
  }

  depends_on = [
    local_file.create_cert_script,
    google_kms_crypto_key.signing_key,
    google_privateca_ca_pool.pool,
    google_project_service.apis 
  ]
}

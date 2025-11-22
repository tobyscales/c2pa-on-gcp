# certificate_provisioner.tf

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
import sys

# Debug: print python path to ensure libraries are found
# print(sys.path)

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
        kms_public_key = None
        # Simple retry loop
        for i in range(5):
            try:
                kms_public_key = client_kms.get_public_key(request={"name": kms_key_full})
                break
            except Exception as e:
                print(f"Attempt {i+1} failed: {e}. Retrying...")
                time.sleep(5)
        
        if not kms_public_key:
            raise Exception("Could not fetch public key after retries")

    except Exception as e:
        print(f"Fatal Error fetching KMS key: {e}")
        sys.exit(1)

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

    # Unique ID to prevent collision on re-runs
    cert_id = f"c2pa-signer-{int(time.time())}"

    request = privateca_v1.CreateCertificateRequest(
        parent=ca_pool_full,
        certificate_id=cert_id,
        certificate=Certificate(config=config, lifetime=lifetime)
    )

    try:
        response = client_ca.create_certificate(request=request)
        print(f"✅ Certificate Created: {response.name}")
    except Exception as e:
        if "already exists" in str(e):
            print(f"ℹ️ Certificate already exists. Skipping.")
        else:
            print(f"❌ Error creating certificate: {e}")
            sys.exit(1)

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

resource "null_resource" "issue_certificate" {
  triggers = {
    key_id  = google_kms_crypto_key.signing_key.id
    pool_id = google_privateca_ca_pool.pool.id
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    
    command = <<EOT
      if ! command -v uv &> /dev/null; then
        echo "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
      fi

      # Force uv to reinstall/sync dependencies to fix broken environments
      uv cache clean
      
      echo "Running cert creation script..."
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

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
from google.cloud import kms
from google.cloud.security import privateca_v1
from google.protobuf import duration_pb2

def create_c2pa_certificate(project_id, location, kms_location, pool_id, key_ring, key_name, key_version, common_name):
    client_kms = kms.KeyManagementServiceClient()
    client_ca = privateca_v1.CertificateAuthorityServiceClient()
    
    # Paths
    kms_key_full = f"projects/{project_id}/locations/{kms_location}/keyRings/{key_ring}/cryptoKeys/{key_name}/cryptoKeyVersions/{key_version}"

    print(f"--- Fetching Public Key from KMS: {key_name} ---")
    try:
        kms_public_key = None
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

    print(f"--- Requesting Certificate from Pool: {pool_id} ---")

    # FIX: Use Python Dictionaries instead of strict Types to avoid ImportError
    # 1 (int) represents the Enum value for PEM format
    config_dict = {
        "public_key": {
            "key": kms_public_key.pem.encode("utf-8"),
            "format": 1  # 1 = PEM
        },
        "subject_config": {
            "subject": {
                "common_name": common_name,
                "organization": "C2PA Signing Org",
                "country_code": "US"
            }
        },
        "x509_config": {
            "key_usage": {
                "base_key_usage": {
                    "digital_signature": True,
                    "content_commitment": True
                }
            }
        }
    }

    # Lifetime: 30 Days
    lifetime = duration_pb2.Duration(seconds=30 * 24 * 60 * 60)
    
    # Unique ID
    cert_id = f"c2pa-signer-{int(time.time())}"

    # Construct the request using a dictionary for the certificate
    request = privateca_v1.CreateCertificateRequest(
        parent=pool_id,
        certificate_id=cert_id,
        certificate={
            "config": config_dict,
            "lifetime": lifetime
        }
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
    parser.add_argument("--kms_location", required=True)
    parser.add_argument("--pool_id", required=True)
    parser.add_argument("--key_ring", required=True)
    parser.add_argument("--key_name", required=True)
    parser.add_argument("--key_version", default="1")
    parser.add_argument("--common_name", default="C2PA Signer")
    args = parser.parse_args()

    create_c2pa_certificate(
        args.project_id, args.location, args.kms_location, args.pool_id, 
        args.key_ring, args.key_name, args.key_version, args.common_name
    )

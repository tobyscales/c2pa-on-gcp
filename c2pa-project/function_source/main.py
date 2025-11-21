import os
import base64
import json
import hashlib
import functions_framework
import c2pa
from google.cloud import storage, secretmanager, kms, privateca_v1
from google.cloud.kms_v1 import ProtectionLevel
from datetime import datetime, timezone

# --- Global Clients (Reuse for warm starts) ---
storage_client = storage.Client()
secret_manager_client = secretmanager.SecretManagerServiceClient()
kms_client = kms.KeyManagementServiceClient()
ca_client = privateca_v1.CertificateAuthorityServiceClient()

class KMSSigner:
    """
    Adapter to sign C2PA manifests using Google Cloud KMS (Asymmetric Key).
    """
    def __init__(self, kms_key_id, public_cert_chain_pem, alg="ps256"):
        self.kms_key_id = kms_key_id
        self.public_cert = public_cert_chain_pem
        self.alg = alg

    def sign(self, data: bytes) -> bytes:
        # 1. Create SHA-256 digest
        digest = hashlib.sha256(data).digest()
        digest_obj = {"sha256": digest}

        # 2. CRC32C for integrity (Best Practice)
        import google_crc32c
        digest_crc32c = google_crc32c.Checksum()
        digest_crc32c.update(digest)

        # 3. Sign via KMS API
        # NOTE: Ensure your KMS Key version is 'RSA_SIGN_PSS_2048_SHA256'
        response = kms_client.asymmetric_sign(
            request={
                "name": self.kms_key_id,
                "digest": digest_obj,
                "digest_crc32c": digest_crc32c.value
            }
        )
        return response.signature

    def public_key(self) -> bytes:
        # C2PA needs the full cert chain (Leaf + Intermediates + Root)
        return self.public_cert.encode('utf-8')

    def algorithm(self) -> str:
        return self.alg

def get_secret(project_id, secret_id, version_id="latest"):
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = secret_manager_client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")

def get_latest_active_cert_chain(ca_pool_full_name):
    """
    Queries the CA Pool for the latest issued, unexpired, and unrevoked certificate.
    Returns the Leaf Certificate concatenated with the Chain (Intermediates).
    """
    print(f"Looking for active certificates in: {ca_pool_full_name}")
    
    # List certificates in the pool
    request = privateca_v1.ListCertificatesRequest(
        parent=ca_pool_full_name,
        order_by="create_time desc", # Get newest first
        filter="revocation_details.revocation_state = ACTIVE" # Only valid certs
    )

    # Iterate through list (we only need the first valid one)
    for cert in ca_client.list_certificates(request=request):
        now = datetime.now(timezone.utc)
        
        # Check expiration
        if cert.expire_time and cert.expire_time < now:
            continue # Skip expired

        # Combine Leaf + Chain
        # pem_certificate is the leaf
        # pem_certificate_chain is the list of intermediates/roots
        full_chain = cert.pem_certificate
        if cert.pem_certificate_chain:
            for intermediate in cert.pem_certificate_chain:
                full_chain += "\n" + intermediate
        
        print(f"Using Certificate: {cert.name}")
        return full_chain

    raise RuntimeError(f"No active certificates found in pool {ca_pool_full_name}")

@functions_framework.cloud_event
def c2pa_sign_pubsub(cloud_event):
    try:
        pubsub_message = cloud_event.data["message"]
        message_data = base64.b64decode(pubsub_message["data"]).decode('utf-8')
        gcs_event = json.loads(message_data)
    except Exception as e:
        print(f"Error parsing event: {e}")
        return

    bucket_name = gcs_event.get('bucket')
    file_name = gcs_event.get('name')

    if not bucket_name or not file_name:
        return

    print(f"Processing {file_name}...")

    # --- Configuration ---
    project_id = os.environ.get('PROJECT_ID')
    kms_key_id = os.environ.get('KMS_KEY_ID') 
    ca_pool_id = os.environ.get('CA_POOL_ID') # Format: projects/.../locations/.../caPools/...
    signed_bucket_name = os.environ.get('SIGNED_BUCKET_NAME')
    
    author_name = get_secret(project_id, os.environ.get('AUTHOR_NAME_SECRET_ID'))
    claim_generator = get_secret(project_id, os.environ.get('CLAIM_GENERATOR_SECRET_ID'))

    # --- Download Source ---
    source_bucket = storage_client.bucket(bucket_name)
    source_blob = source_bucket.blob(file_name)
    temp_input = f"/tmp/{file_name}"
    temp_output = f"/tmp/signed-{file_name}"
    source_blob.download_to_filename(temp_input)

    try:
        # --- 1. Fetch Cert Chain ---
        # This dynamically grabs the valid cert for the manifest
        cert_chain_pem = get_latest_active_cert_chain(ca_pool_id)

        # --- 2. Initialize Signer ---
        # Uses Remote KMS Signing + Local Cert Chain
        kms_signer = KMSSigner(kms_key_id, cert_chain_pem, alg="ps256")

        # --- 3. Build Manifest ---
        manifest_json = json.dumps({
            "claim_generator": claim_generator,
            "assertions": [
                {
                    "label": "c2pa.actions",
                    "data": {"actions": [{"action": "c2pa.created"}]}
                },
                {
                    "label": "stds.schema-org.CreativeWork",
                    "data": {
                        "@context": "https://schema.org",
                        "author": [{"@type": "Person", "name": author_name}]
                    }
                }
            ]
        })

        # --- 4. Sign ---
        c2pa.sign(
            source=temp_input,
            dest=temp_output,
            manifest=manifest_json,
            signer=kms_signer,
            data_dir=None
        )

        # --- 5. Upload ---
        dest_bucket = storage_client.bucket(signed_bucket_name)
        dest_blob = dest_bucket.blob(file_name)
        dest_blob.upload_from_filename(temp_output)
        print(f"Success: Signed {file_name}")

    except Exception as e:
        print(f"Signing failed: {e}")
    finally:
        # Cleanup
        if os.path.exists(temp_input): os.remove(temp_input)
        if os.path.exists(temp_output): os.remove(temp_output)

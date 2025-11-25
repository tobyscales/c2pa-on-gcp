import os
import json
import hashlib
import functions_framework
import c2pa
from google.cloud import storage, secretmanager, kms
from google.cloud.security import privateca_v1
# Explicitly import crc32c to ensure it's available
import google_crc32c 

from datetime import datetime, timezone

# --- Global Clients ---
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

        # 2. CRC32C for integrity
        digest_crc32c = google_crc32c.Checksum()
        digest_crc32c.update(digest)

        # 3. Sign via KMS API
        response = kms_client.asymmetric_sign(
            request={
                "name": self.kms_key_id,
                "digest": digest_obj,
                "digest_crc32c": digest_crc32c.value
            }
        )
        return response.signature

    def public_key(self) -> bytes:
        return self.public_cert.encode('utf-8')

    def algorithm(self) -> str:
        return self.alg

def get_secret(project_id, secret_id, version_id="latest"):
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = secret_manager_client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")

def get_latest_active_cert_chain(ca_pool_full_name):
    print(f"Looking for active certificates in: {ca_pool_full_name}")
    
    # FIX: Remove 'order_by'. The API does not support it.
    request = privateca_v1.ListCertificatesRequest(
        parent=ca_pool_full_name,
        filter="revocation_details.revocation_state = ACTIVE"
    )

    # 1. Fetch all active certs
    certs = list(ca_client.list_certificates(request=request))
    
    # 2. Sort client-side (Newest created first)
    # The client library converts protobuf timestamps to Python datetime automatically
    certs.sort(key=lambda x: x.create_time, reverse=True)

    # 3. Iterate to find the first unexpired one
    now = datetime.now(timezone.utc)
    
    for cert in certs:
        if cert.expire_time and cert.expire_time < now:
            continue 

        full_chain = cert.pem_certificate
        if cert.pem_certificate_chain:
            for intermediate in cert.pem_certificate_chain:
                full_chain += "\n" + intermediate
        
        print(f"Using Certificate: {cert.name}")
        return full_chain

    raise RuntimeError(f"No active, unexpired certificates found in pool {ca_pool_full_name}")
    
@functions_framework.cloud_event
def c2pa_sign_pubsub(cloud_event):
    """
    TRIGGER: google.cloud.storage.object.v1.finalized (Eventarc)
    PAYLOAD: The raw storage object metadata (dict)
    """
    data = cloud_event.data

    # --- FIX: Direct access to bucket/name (No PubSub decoding) ---
    bucket_name = data.get("bucket")
    file_name = data.get("name")

    if not bucket_name or not file_name:
        print(f"⚠️ Event ignored: Missing bucket/name. Data keys: {list(data.keys())}")
        return

    print(f"Processing {file_name} from {bucket_name}...")

    # --- Configuration ---
    project_id = os.environ.get('PROJECT_ID')
    kms_key_id = os.environ.get('KMS_KEY_ID') 
    ca_pool_id = os.environ.get('CA_POOL_ID') 
    signed_bucket_name = os.environ.get('SIGNED_BUCKET_NAME')
    
    # Validation
    if bucket_name == signed_bucket_name:
        print("⚠️ Loop protection: Ignoring event from the signed bucket.")
        return

    try:
        author_name = get_secret(project_id, os.environ.get('AUTHOR_NAME_SECRET_ID'))
        claim_generator = get_secret(project_id, os.environ.get('CLAIM_GENERATOR_SECRET_ID'))

        # --- Download Source ---
        source_bucket = storage_client.bucket(bucket_name)
        source_blob = source_bucket.blob(file_name)
        temp_input = f"/tmp/{file_name}"
        temp_output = f"/tmp/signed-{file_name}"
        
        # Ensure clean slate
        if os.path.exists(temp_input): os.remove(temp_input)
        if os.path.exists(temp_output): os.remove(temp_output)
        
        source_blob.download_to_filename(temp_input)

        # --- Sign ---
        cert_chain_pem = get_latest_active_cert_chain(ca_pool_id)
        kms_signer = KMSSigner(kms_key_id, cert_chain_pem, alg="ps256")

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

        c2pa.sign(
            source=temp_input,
            dest=temp_output,
            manifest=manifest_json,
            signer=kms_signer,
            data_dir=None
        )

        # --- Upload ---
        dest_bucket = storage_client.bucket(signed_bucket_name)
        dest_blob = dest_bucket.blob(file_name)
        dest_blob.upload_from_filename(temp_output)
        print(f"✅ Success: Signed and uploaded {file_name}")

    except Exception as e:
        # Print full stack trace for debugging
        import traceback
        traceback.print_exc()
        print(f"❌ Signing failed: {e}")
    finally:
        if os.path.exists(temp_input): os.remove(temp_input)
        if os.path.exists(temp_output): os.remove(temp_output)
import os
import base64
import json
import hashlib
import functions_framework
import c2pa
from google.cloud import storage, secretmanager, kms
from google.cloud.kms_v1 import ProtectionLevel

# Instantiate clients globally
storage_client = storage.Client()
secret_manager_client = secretmanager.SecretManagerServiceClient()
kms_client = kms.KeyManagementServiceClient()

class KMSSigner:
    """
    Custom Signer adapter that delegates signing to Google Cloud KMS.
    The private key never leaves KMS.
    """
    def __init__(self, kms_key_id, public_cert_pem, alg="ps256"):
        self.kms_key_id = kms_key_id
        self.public_cert = public_cert_pem
        self.alg = alg

    def sign(self, data: bytes) -> bytes:
        """
        Callback invoked by the C2PA library. 
        1. Hashes the data (SHA-256).
        2. Sends the hash to Cloud KMS to be signed.
        """
        # 1. Calculate SHA-256 digest of the data
        digest = hashlib.sha256(data).digest()
        
        # 2. Construct the digest object for KMS
        # Note: Adjust 'sha256' if using a different key algorithm
        digest_obj = {"sha256": digest}

        # 3. Call KMS AsymmetricSign
        # We create a CRC32C checksum for data integrity (best practice for KMS)
        import google_crc32c
        digest_crc32c = google_crc32c.Checksum()
        digest_crc32c.update(digest)

        response = kms_client.asymmetric_sign(
            request={
                "name": self.kms_key_id,
                "digest": digest_obj,
                "digest_crc32c": digest_crc32c.value
            }
        )
        
        return response.signature

    def public_key(self) -> bytes:
        """Returns the public certificate PEM bytes."""
        return self.public_cert.encode('utf-8')

    def algorithm(self) -> str:
        return self.alg


def get_secret(project_id, secret_id, version_id="latest"):
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = secret_manager_client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")

def get_public_cert(ca_pool_id):
    """
    Retrieves the Public Certificate from the CA Pool or Secret Manager.
    For this example, we assume the certificate PEM is stored in a Secret 
    or retrieved via the Private CA API. 
    """
    # NOTE: Implementation depends on where you store your leaf certificate.
    # You might generate a new one via PrivateCA API on the fly, or read a static one.
    # Returning a placeholder for demonstration.
    # In production: calling privateca_v1.CertificateAuthorityServiceClient to get the cert.
    return "-----BEGIN CERTIFICATE-----\n(Your Public Cert Content)\n-----END CERTIFICATE-----"


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

    # Config
    project_id = os.environ.get('PROJECT_ID')
    kms_key_id = os.environ.get('KMS_KEY_ID')
    ca_pool_id = os.environ.get('CA_POOL_ID')
    signed_bucket_name = os.environ.get('SIGNED_BUCKET_NAME')
    
    author_name = get_secret(project_id, os.environ.get('AUTHOR_NAME_SECRET_ID'))
    claim_generator = get_secret(project_id, os.environ.get('CLAIM_GENERATOR_SECRET_ID'))

    # Setup Files
    source_bucket = storage_client.bucket(bucket_name)
    source_blob = source_bucket.blob(file_name)
    temp_input = f"/tmp/{file_name}"
    temp_output = f"/tmp/signed-{file_name}"
    source_blob.download_to_filename(temp_input)

    # --- Signing Setup ---
    
    # 1. Get the Public Certificate (PEM) associated with the KMS key
    # You must ensure this cert matches the Key Pair in KMS
    public_cert_pem = get_public_cert(ca_pool_id)

    # 2. Initialize our Custom KMS Signer
    # ensure your KMS key is RSA-PSS 2048 or 4096 SHA-256 for "ps256"
    kms_signer = KMSSigner(kms_key_id, public_cert_pem, alg="ps256")

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

    try:
        # 3. Sign using the custom signer
        # c2pa-python (recent versions) supports passing a custom signer object
        c2pa.sign(
            source=temp_input,
            dest=temp_output,
            manifest=manifest_json,
            signer=kms_signer, # Pass the instance of our custom class
            data_dir=None
        )

        # Upload
        dest_bucket = storage_client.bucket(signed_bucket_name)
        dest_blob = dest_bucket.blob(file_name)
        dest_blob.upload_from_filename(temp_output)
        print(f"Success: {file_name}")

    except Exception as e:
        print(f"Signing failed: {e}")
        # Clean up temp files
        if os.path.exists(temp_input): os.remove(temp_input)
        if os.path.exists(temp_output): os.remove(temp_output)
        raise e

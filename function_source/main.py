# function_source/main.py

import os
import base64
import json
import c2pa
from google.cloud import storage, privateca_v1, kms_v1

def c2pa_sign_pubsub(event, context):
    """
    Cloud Function to be triggered by a Pub/Sub message from a GCS notification.
    """
    # --- Parse Pub/Sub Message ---
    if 'data' in event:
        # Decode the Pub/Sub message
        message_data = base64.b64decode(event['data']).decode('utf-8')
        gcs_event = json.loads(message_data)
        bucket_name = gcs_event['bucket']
        file_name = gcs_event['name']
        print(f"Processing file {file_name} from bucket {bucket_name}.")
    else:
        print("No data in Pub/Sub message; exiting.")
        return

    # --- C2PA Signing Logic (remains the same) ---
    kms_key_id = os.environ.get('KMS_KEY_ID')
    ca_pool_id = os.environ.get('CA_POOL_ID')
    signed_bucket_name = os.environ.get('SIGNED_BUCKET_NAME')

    storage_client = storage.Client()
    source_bucket = storage_client.bucket(bucket_name)
    source_blob = source_bucket.blob(file_name)
    
    temp_file_path = f"/tmp/{file_name}"
    source_blob.download_to_filename(temp_file_path)
    
    manifest = {
        "alg": "ps256",
        "claim_generator": "My-Resilient-GCP-C2PA-Signer/0.2",
        "assertions": [
            {
                "label": "stds.schema-org.CreativeWork",
                "data": {
                    "@context": "https://schema.org",
                    "author": [{"@type": "Person", "name": "Your Name or Organization"}]
                }
            }
        ]
    }
    
    cert_pem, private_key_pem, public_key_pem = create_certificate(ca_pool_id, kms_key_id)
    
    # The CAS client is smart enough to find an available CA in the specified pool
    signer = c2pa.Signer.from_pem(private_key_pem, cert_pem, "ps256", kms_key_id)

    c2pa.sign_file(temp_file_path, f"/tmp/signed-{file_name}", manifest, signer)

    destination_bucket = storage_client.bucket(signed_bucket_name)
    destination_blob = destination_bucket.blob(file_name)
    destination_blob.upload_from_filename(f"/tmp/signed-{file_name}")
    
    print(f"File {file_name} signed and uploaded to {signed_bucket_name}.")

def create_certificate(ca_pool_id, kms_key_id):
    # This placeholder function remains the same.
    # In a real implementation, the CAS client would be directed to the CA pool ID
    # and would automatically failover to an available CA within that pool.
    print(f"Requesting certificate from CA Pool: {ca_pool_id}")
    private_key_pem = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
    public_key_pem = "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"
    cert_pem = "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n"
    
    print("Certificate created.")
    return cert_pem, private_key_pem, public_key_pem

# function_source/main.py

import os
import base64
import json
import c2pa
from google.cloud import storage, privateca_v1, kms_v1, secretmanager

# Instantiate clients outside the function handler for reuse
storage_client = storage.Client()
secret_manager_client = secretmanager.SecretManagerServiceClient()

def get_secret(project_id, secret_id, version_id="latest"):
    """
    Retrieves a secret's payload from Google Secret Manager.
    """
    # Build the resource name of the secret version.
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    
    # Access the secret version.
    response = secret_manager_client.access_secret_version(name=name)
    
    # Return the decoded payload.
    return response.payload.data.decode("UTF-8")

def c2pa_sign_pubsub(event, context):
    """
    Cloud Function to be triggered by a Pub/Sub message from a GCS notification.
    """
    if 'data' not in event:
        print("No data in Pub/Sub message; exiting.")
        return

    message_data = base64.b64decode(event['data']).decode('utf-8')
    gcs_event = json.loads(message_data)
    bucket_name = gcs_event['bucket']
    file_name = gcs_event['name']
    print(f"Processing file {file_name} from bucket {bucket_name}.")

    # --- Read configuration from environment and Secret Manager ---
    project_id = os.environ.get('PROJECT_ID')
    kms_key_id = os.environ.get('KMS_KEY_ID')
    ca_pool_id = os.environ.get('CA_POOL_ID')
    signed_bucket_name = os.environ.get('SIGNED_BUCKET_NAME')
    
    # Get secret IDs from environment variables
    author_secret_id = os.environ.get('AUTHOR_NAME_SECRET_ID')
    generator_secret_id = os.environ.get('CLAIM_GENERATOR_SECRET_ID')

    # Fetch secret values from Secret Manager
    author_name = get_secret(project_id, author_secret_id)
    claim_generator = get_secret(project_id, generator_secret_id)

    # --- Dynamically create the C2PA manifest ---
    manifest = {
        "alg": "ps256",
        "claim_generator": claim_generator,
        "assertions": [
            {
                "label": "stds.schema-org.CreativeWork",
                "data": {
                    "@context": "https://schema.org",
                    "author": [{"@type": "Person", "name": author_name}],
                    "copyrightHolder": [{"@type": "Person", "name": author_name}]
                }
            }
        ]
    }
    
    source_bucket = storage_client.bucket(bucket_name)
    source_blob = source_bucket.blob(file_name)
    
    temp_file_path = f"/tmp/{file_name}"
    source_blob.download_to_filename(temp_file_path)
    
    cert_pem, private_key_pem, public_key_pem = create_certificate(ca_pool_id, kms_key_id)
    
    signer = c2pa.Signer.from_pem(private_key_pem, cert_pem, "ps256", kms_key_id)
    c2pa.sign_file(temp_file_path, f"/tmp/signed-{file_name}", manifest, signer)

    destination_bucket = storage_client.bucket(signed_bucket_name)
    destination_blob = destination_bucket.blob(file_name)
    destination_blob.upload_from_filename(f"/tmp/signed-{file_name}")
    
    print(f"File {file_name} signed with author '{author_name}' and uploaded to {signed_bucket_name}.")

def create_certificate(ca_pool_id, kms_key_id):
    # This placeholder function remains the same.
    # ...
    return "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n", \
           "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n", \
           "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"

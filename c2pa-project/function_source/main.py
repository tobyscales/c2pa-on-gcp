# function_source/main.py

import os
import base64
import json
import functions_framework
import c2pa
from google.cloud import storage, secretmanager

# Instantiate clients globally for reuse across warm starts
storage_client = storage.Client()
secret_manager_client = secretmanager.SecretManagerServiceClient()

def get_secret(project_id, secret_id, version_id="latest"):
    """Retrieves a secret's payload from Google Secret Manager."""
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = secret_manager_client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")

@functions_framework.cloud_event
def c2pa_sign_pubsub(cloud_event):
    """
    Cloud Function (Gen 2) triggered by a Pub/Sub message via Eventarc.
    The Pub/Sub message contains the GCS notification data.
    """
    
    # 1. Unpack the CloudEvent data
    # Pub/Sub data is wrapped in the cloud_event.data object
    try:
        pubsub_message = cloud_event.data["message"]
        message_data = base64.b64decode(pubsub_message["data"]).decode('utf-8')
        gcs_event = json.loads(message_data)
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"Error parsing Pub/Sub message: {e}")
        return

    bucket_name = gcs_event.get('bucket')
    file_name = gcs_event.get('name')

    if not bucket_name or not file_name:
        print("Missing bucket or filename in GCS event.")
        return

    print(f"Processing file {file_name} from bucket {bucket_name}.")

    # --- Read configuration ---
    project_id = os.environ.get('PROJECT_ID')
    kms_key_id = os.environ.get('KMS_KEY_ID')
    ca_pool_id = os.environ.get('CA_POOL_ID')
    signed_bucket_name = os.environ.get('SIGNED_BUCKET_NAME')
    author_secret_id = os.environ.get('AUTHOR_NAME_SECRET_ID')
    generator_secret_id = os.environ.get('CLAIM_GENERATOR_SECRET_ID')

    # --- Fetch Secrets ---
    try:
        author_name = get_secret(project_id, author_secret_id)
        claim_generator = get_secret(project_id, generator_secret_id)
    except Exception as e:
        print(f"Failed to retrieve secrets: {e}")
        raise e

    # --- Create Manifest ---
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
    
    # --- Download Source ---
    source_bucket = storage_client.bucket(bucket_name)
    source_blob = source_bucket.blob(file_name)
    
    temp_file_path = f"/tmp/{file_name}"
    source_blob.download_to_filename(temp_file_path)
    
    # --- Signing Logic ---
    # Note: Ensure create_certificate returns PEM strings compatible with c2pa library
    cert_pem, private_key_pem, public_key_pem = create_certificate(ca_pool_id, kms_key_id)
    
    try:
        signer = c2pa.Signer.from_pem(private_key_pem, cert_pem, "ps256", kms_key_id)
        signed_output_path = f"/tmp/signed-{file_name}"
        
        c2pa.sign_file(temp_file_path, signed_output_path, manifest, signer)

        # --- Upload Result ---
        destination_bucket = storage_client.bucket(signed_bucket_name)
        destination_blob = destination_bucket.blob(file_name)
        destination_blob.upload_from_filename(signed_output_path)
        
        print(f"File {file_name} signed successfully and uploaded to {signed_bucket_name}.")

    except Exception as e:
        print(f"Error during signing process: {e}")
        raise e

def create_certificate(ca_pool_id, kms_key_id):
    # Placeholder for Certificate Authority Service logic
    # This needs to return real PEM data for the signer to work
    return (
        "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n",
        "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
        "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"
    )

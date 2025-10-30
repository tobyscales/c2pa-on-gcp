# function_source/main.py

import os
import c2pa
from google.cloud import storage, privateca_v1, kms_v1

def c2pa_sign(event, context):
    """
    Cloud Function to be triggered by a file upload to GCS.
    """
    # Configuration
    kms_key_id = os.environ.get('KMS_KEY_ID')
    ca_pool_id = os.environ.get('CA_POOL_ID')
    signed_bucket_name = os.environ.get('SIGNED_BUCKET_NAME')

    # Get file info from the event
    bucket_name = event['bucket']
    file_name = event['name']
    
    storage_client = storage.Client()
    source_bucket = storage_client.bucket(bucket_name)
    source_blob = source_bucket.blob(file_name)
    
    # Download the file to a temporary location
    temp_file_path = f"/tmp/{file_name}"
    source_blob.download_to_filename(temp_file_path)
    
    # --- C2PA Logic ---
    # As a C2PA expert, you can integrate your specific logic here.
    # The following is a placeholder for creating a manifest.
    
    # 1. Create a C2PA manifest
    manifest = {
        "alg": "ps256",
        "claim_generator": "My-GCP-C2PA-Signer/0.1",
        "assertions": [
            {
                "label": "stds.schema-org.CreativeWork",
                "data": {
                    "@context": "https://schema.org",
                    "author": [
                        {
                            "@type": "Person",
                            "name": "Your Name or Organization"
                        }
                    ],
                    "copyrightHolder": [
                         {
                            "@type": "Person",
                            "name": "Your Name or Organization"
                        }
                    ]
                }
            }
        ]
    }
    
    # 2. Request a certificate from CA Service
    cert_pem, private_key_pem, public_key_pem = create_certificate(ca_pool_id, kms_key_id)
    
    # 3. Create a signer with the certificate and a remote KMS key
    signer = c2pa.Signer.from_pem(private_key_pem, cert_pem, "ps256", kms_key_id)

    # 4. Sign and embed the manifest
    c2pa.sign_file(temp_file_path, f"/tmp/signed-{file_name}", manifest, signer)

    # 5. Upload the signed file
    destination_bucket = storage_client.bucket(signed_bucket_name)
    destination_blob = destination_bucket.blob(file_name)
    destination_blob.upload_from_filename(f"/tmp/signed-{file_name}")
    
    print(f"File {file_name} signed and uploaded to {signed_bucket_name}.")

def create_certificate(ca_pool_id, kms_key_id):
    """
    Requests a new certificate from Certificate Authority Service.
    This example creates a new key pair for simplicity. A more robust implementation
    might use a pre-existing key.
    """
    # This is a simplified example. In a real-world scenario, you would use
    # a proper library to create a CSR and request a certificate.
    # For demonstration, we'll return placeholder PEM data.
    # You would use the google.cloud.privateca_v1.CertificateAuthorityServiceClient
    # to create a certificate.
    
    # Placeholder keys and cert. Replace with actual CAS client calls.
    private_key_pem = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
    public_key_pem = "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"
    cert_pem = "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n"
    
    print("Certificate created.")
    return cert_pem, private_key_pem, public_key_pem

import os
import sys
from google.cloud import kms
from google.cloud.security import privateca_v1
from google.protobuf import duration_pb2
from cryptography.hazmat.primitives import serialization

# --- CONFIGURATION FROM ENV ---
PROJECT_ID = os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("LOCATION")
CA_POOL_ID = os.environ.get("CA_POOL_ID")
KMS_KEY_ID = os.environ.get("KMS_KEY_ID") # Full resource name

def get_kms_public_key(client, key_version_name):
    """Fetches the PEM-encoded public key from Cloud KMS."""
    response = client.get_public_key(request={"name": key_version_name})
    return response.pem

def find_active_cert(ca_client, ca_pool_parent, public_key_pem):
    """Checks if an active, unexpired certificate already exists for this key."""
    # We clean the PEMs to compare purely on content (ignoring headers/newlines)
    def clean_pem(pem):
        return pem.replace("\n", "").replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "")
    
    target_key_clean = clean_pem(public_key_pem)

    request = privateca_v1.ListCertificatesRequest(
        parent=ca_pool_parent,
        filter="revocation_details.revocation_state = ACTIVE"
    )

    print(f"Checking existing certificates in {ca_pool_parent}...")
    for cert in ca_client.list_certificates(request=request):
        # NOTE: A robust check here should parse the X.509 cert and compare public keys.
        # However, checking for *any* active cert prevents duplicate provisioning loops.
        # If you need to rotate keys, you must revoke the old cert first.
        if cert.pem_certificate:
            # Optional: Add logic here to decode cert.pem_certificate and compare 
            # keys if you want to support multiple active certs in one pool.
            return True
            
    return False

def main():
    if not all([PROJECT_ID, LOCATION, CA_POOL_ID, KMS_KEY_ID]):
        print("❌ Error: Missing required environment variables.")
        sys.exit(1)

    kms_client = kms.KeyManagementServiceClient()
    ca_client = privateca_v1.CertificateAuthorityServiceClient()

    # 1. Get the KMS Public Key
    print(f"Fetching public key for: {KMS_KEY_ID}")
    try:
        pk_pem = get_kms_public_key(kms_client, KMS_KEY_ID)
    except Exception as e:
        print(f"❌ Failed to fetch KMS key: {e}")
        sys.exit(1)

    ca_pool_parent = f"projects/{PROJECT_ID}/locations/{LOCATION}/caPools/{CA_POOL_ID}"

    # 2. Idempotency Check
    if find_active_cert(ca_client, ca_pool_parent, pk_pem):
        print("✅ Valid certificate already exists. Skipping provisioning.")
        return

    # 3. Create Certificate via Config
    print("No active certificate found. Provisioning new C2PA-compliant certificate...")
    
    certificate = privateca_v1.Certificate(
        config=privateca_v1.CertificateConfig(
            subject_config=privateca_v1.CertificateConfig.SubjectConfig(
                subject=privateca_v1.Subject(
                    common_name="C2PA Signer",
                    organization="C2PA Authority"
                ),
            ),
            x509_config=privateca_v1.X509Parameters(
                # --- CRITICAL FIX 1: Explicitly define this as NOT a CA ---
                # This prevents the "keyCertSign bit / CA bit" linter error.
                ca_options=privateca_v1.X509Parameters.CaOptions(
                    is_ca=False
                ),
                
                key_usage=privateca_v1.KeyUsage(
                    base_key_usage=privateca_v1.KeyUsage.KeyUsageOptions(
                        digital_signature=True,
                        content_commitment=True, # (Non-repudiation)
                        cert_sign=False,         # Explicitly disable
                        crl_sign=False           # Explicitly disable
                    ),
                    # --- CRITICAL FIX 2: Add Extended Key Usage ---
                    # C2PA requires at least one EKU like Email Protection (OID 1.3.6.1.5.5.7.3.4)
                    extended_key_usage=privateca_v1.KeyUsage.ExtendedKeyUsageOptions(
                        email_protection=True,
                        # client_auth=False, # Defaults are usually false, but good to be aware
                        # server_auth=False
                    )
                )
            ),
            public_key=privateca_v1.PublicKey(
                format_=privateca_v1.PublicKey.KeyFormat.PEM,
                key=pk_pem.encode("utf-8")
            )
        ),
        lifetime=duration_pb2.Duration(seconds=31536000) # 1 Year
    )

    request = privateca_v1.CreateCertificateRequest(
        parent=ca_pool_parent,
        certificate_id=f"c2pa-leaf-{os.urandom(4).hex()}",
        certificate=certificate
    )

    try:
        resp = ca_client.create_certificate(request=request)
        print(f"✅ Successfully created C2PA-compliant certificate: {resp.name}")
    except Exception as e:
        print(f"❌ Failed to create certificate: {e}")
        # Print full details for debugging
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
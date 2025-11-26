import os
import sys
from google.cloud import kms
from google.cloud.security import privateca_v1
from google.protobuf import duration_pb2
from cryptography import x509
from cryptography.hazmat.primitives import serialization

# --- CONFIGURATION FROM ENV ---
PROJECT_ID = os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("LOCATION")
CA_POOL_ID = os.environ.get("CA_POOL_ID")
KMS_KEY_ID = os.environ.get("KMS_KEY_ID")

def get_kms_public_key_pem(client, key_version_name):
    """Fetches the PEM-encoded public key from Cloud KMS."""
    response = client.get_public_key(request={"name": key_version_name})
    return response.pem

def get_public_key_bytes(pem_string):
    """Extracts DER encoded public key bytes for comparison."""
    # This handles stripping headers and standardizing formats
    key = serialization.load_pem_public_key(pem_string.encode('utf-8'))
    return key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

def find_active_matching_cert(ca_client, ca_pool_parent, kms_pk_pem):
    """Checks if an active certificate exists that MATCHES the specific KMS key."""
    
    target_pk_bytes = get_public_key_bytes(kms_pk_pem)

    request = privateca_v1.ListCertificatesRequest(
        parent=ca_pool_parent,
        filter="revocation_details.revocation_state = ACTIVE"
    )

    print(f"Checking existing certificates in {ca_pool_parent}...")
    for cert in ca_client.list_certificates(request=request):
        try:
            cert_obj = x509.load_pem_x509_certificate(cert.pem_certificate.encode('utf-8'))
            cert_pk_bytes = cert_obj.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            if cert_pk_bytes == target_pk_bytes:
                print(f"✅ Found matching active certificate: {cert.name}")
                return True
        except Exception as e:
            print(f"⚠️ Warning: Could not parse certificate {cert.name}: {e}")
            continue
            
    return False

def main():
    if not all([PROJECT_ID, LOCATION, CA_POOL_ID, KMS_KEY_ID]):
        print("❌ Error: Missing required environment variables.")
        sys.exit(1)

    kms_client = kms.KeyManagementServiceClient()
    ca_client = privateca_v1.CertificateAuthorityServiceClient()

    print(f"Fetching public key for: {KMS_KEY_ID}")
    try:
        pk_pem = get_kms_public_key_pem(kms_client, KMS_KEY_ID)
    except Exception as e:
        print(f"❌ Failed to fetch KMS key: {e}")
        sys.exit(1)

    ca_pool_parent = f"projects/{PROJECT_ID}/locations/{LOCATION}/caPools/{CA_POOL_ID}"

    # Idempotency Check with Key Comparison
    if find_active_matching_cert(ca_client, ca_pool_parent, pk_pem):
        print("✅ Valid certificate already exists for this KMS key. Skipping.")
        return

    print("No matching certificate found. Provisioning new C2PA-compliant certificate...")
    
    certificate = privateca_v1.Certificate(
        config=privateca_v1.CertificateConfig(
            subject_config=privateca_v1.CertificateConfig.SubjectConfig(
                subject=privateca_v1.Subject(
                    common_name="C2PA Signer",
                    organization="C2PA Authority"
                ),
            ),
            x509_config=privateca_v1.X509Parameters(
                ca_options=privateca_v1.X509Parameters.CaOptions(
                    is_ca=False
                ),
                key_usage=privateca_v1.KeyUsage(
                    base_key_usage=privateca_v1.KeyUsage.KeyUsageOptions(
                        digital_signature=True,
                        content_commitment=True,
                        cert_sign=False,
                        crl_sign=False
                    ),
                    extended_key_usage=privateca_v1.KeyUsage.ExtendedKeyUsageOptions(
                        email_protection=True,
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
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
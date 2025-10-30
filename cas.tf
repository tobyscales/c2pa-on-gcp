# cas.tf

resource "google_privateca_ca_pool" "pool" {
  name     = "c2pa-ca-pool"
  location = var.region
  tier     = "DEVOPS"
  project  = var.project_id
}

resource "google_privateca_certificate_authority" "root_ca" {
  pool                     = google_privateca_ca_pool.pool.name
  certificate_authority_id = "c2pa-root-ca"
  location                 = var.region
  project                  = var.project_id
  type                     = "SELF_SIGNED"
  key_spec {
    algorithm = "RSA_PKCS1_4096_SHA256"
  }
  config {
    subject_config {
      subject = {
        organization = "C2PA Signing Authority"
        common_name  = "c2pa-root-ca"
      }
    }
    x509_config {
      ca_options {
        is_ca = true
      }
      key_usage {
        base_key_usage {
          cert_sign = true
          crl_sign  = true
        }
        extended_key_usage {
          server_auth = false
        }
      }
    }
  }
  lifetime = "8760h" # 1 year
}

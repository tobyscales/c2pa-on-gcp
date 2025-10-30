# cas.tf

resource "google_privateca_ca_pool" "pool" {
  name     = "c2pa-ca-pool"
  location = var.regions[0] # Place the pool in the primary region
  tier     = "DEVOPS"
  project  = var.project_id
}

resource "google_privateca_certificate_authority" "regional_ca" {
  for_each = toset(var.regions)

  pool                     = google_privateca_ca_pool.pool.name
  certificate_authority_id = "c2pa-ca-${each.value}"
  location                 = each.value # Create a CA in each region
  project                  = var.project_id
  #type                     = "SUBORDINATE" # Subordinate to a root or another intermediate
  
  # For production, you would create a self-signed root CA separately and have
  # these subordinates chained to it. For this example, we make them self-signed for simplicity.
  # In a true subordinate setup, you'd define a `subordinate_config` block.
  config {
    subject_config {
      subject {
        organization = "C2PA Signing Authority"
        common_name  = "C2PA Regional CA ${each.value}"
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
        }
      }
    }
  }
  key_spec {
    algorithm = "RSA_PKCS1_4096_SHA256"
  }
  
  lifetime = "8760h" # 1 year

  # Ensure the pool exists before creating the CA
  depends_on = [google_privateca_ca_pool.pool]
}

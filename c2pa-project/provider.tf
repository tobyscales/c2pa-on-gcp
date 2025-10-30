terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }

  # --- Partial Backend Configuration ---
  # The bucket name will be supplied dynamically during initialization.
  backend "gcs" {
    prefix = "c2pa-signer/state"
  }
}


# This is your default provider, likely configured for a single region
provider "google" {
  project = var.project_id
  region  = var.regions[0]
}

# ADD THIS ALIAS: A provider specifically for multi-regional resources
provider "google" {
  alias   = "multi_region_provider"
  project = var.project_id
  # This can be set to any region within the multi-region, 
  # but setting it to the multi-region itself is clearer.
  region  = var.multi_region_location 
}
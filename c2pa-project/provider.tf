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

# The rest of your provider configuration...
provider "google" {
  project = var.project_id
  region  = var.regions[0]
}

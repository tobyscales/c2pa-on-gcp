# main.tf

# main.tf

# First, create a dedicated resource for the foundational API
resource "google_project_service" "cloudresourcemanager" {
  project = var.project_id
  service = "cloudresourcemanager.googleapis.com"
  
  # This setting prevents Terraform from trying to destroy this foundational API
  disable_on_destroy = false
}

# Now, make all your other service activations explicitly depend on the first one.
resource "google_project_service" "apis" {
  for_each = toset([
    "storage.googleapis.com",
    "cloudkms.googleapis.com",
    "privateca.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "run.googleapis.com",
    "eventarc.googleapis.com"
  ])

  project = var.project_id
  service = each.key
  
  disable_on_destroy = false
  
  # Tells Terraform to wait until the Cloud Resource Manager API is enabled
  depends_on = [
    google_project_service.cloudresourcemanager
  ]
}

resource "random_id" "suffix" {
  byte_length = 4
}



# variables.tf

variable "project_id" {
  description = "The GCP project ID."
  type        = string
}

variable "regions" {
  description = "A list of GCP regions for deploying resilient resources."
  type        = list(string)
  default     = ["us-central1", "us-east1"]
}

variable "multi_region_location" {
  description = "The multi-region location for GCS and KMS (e.g., US, EU, ASIA)."
  type        = string
  default     = "US"
}

# variables.tf

variable "project_id" {
  description = "The GCP project ID."
  type        = string
}

variable "region" {
  description = "The GCP region for deployment."
  type        = string
  default     = "us-central1"
}

variable "location" {
  description = "The GCP location for GCS and CAS."
  type        = string
  default     = "US"
}

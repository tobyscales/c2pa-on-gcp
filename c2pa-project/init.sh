#!/bin/bash

# A wrapper script to securely initialize Terraform by fetching the
# backend bucket name from Google Secret Manager.

# Exit immediately if a command exits with a non-zero status.
set -e

if [ -z "$1" ]; then
  echo "Error: Please provide your GCP Project ID as the first argument."
  echo "Usage: ./init.sh <your-gcp-project-id>"
  exit 1
fi

PROJECT_ID=$1
SECRET_ID="tfstate-bucket-name" # This must match the secret_id from the bootstrap project

echo "Fetching backend bucket name from Secret Manager..."

# Use gcloud to access the latest version of the secret.
# The output of this command is the raw bucket name.
BUCKET_NAME=$(gcloud secrets versions access latest \
  --secret="${SECRET_ID}" \
  --project="${PROJECT_ID}" \
  --format='get(payload.data)' | tr -d '\n' | base64 -d)

if [ -z "$BUCKET_NAME" ]; then
  echo "Error: Could not fetch bucket name from Secret Manager."
  echo "Ensure the secret '${SECRET_ID}' exists in project '${PROJECT_ID}'."
  exit 1
fi

echo "Successfully fetched bucket name: ${BUCKET_NAME}"
echo "------------------------------------------------"
echo "Initializing Terraform with remote GCS backend..."

# Initialize Terraform, passing the fetched bucket name via the -backend-config flag.
terraform init \
  -backend-config="bucket=${BUCKET_NAME}"

echo "------------------------------------------------"
echo "Terraform initialization complete."

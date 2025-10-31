
# Enterprise-Grade GCP C2PA Signing Service

This repository contains a complete Terraform project to deploy a regionally-resilient, secure, and automated service on Google Cloud Platform for signing digital content with C2PA manifests.

The solution is designed with enterprise best practices in mind, including secure state management, CI/CD-friendly configuration, and least-privilege IAM principles.

## Features

*   **Automated Workflow**: Upload a file to a GCS bucket, and a signed version automatically appears in another.
*   **Regionally Resilient**: Utilizes multi-regional GCS/KMS and deploys compute resources across multiple regions to withstand a single regional outage.
*   **Secure by Design**: Leverages a hardware-backed Cloud KMS key for signing, manages configuration securely via Secret Manager, and uses a private Certificate Authority (CA) for certificate issuance.

## Architectural Overview

The workflow is event-driven and orchestrated by loosely coupled Google Cloud services:

1.  **Upload**: A user or application uploads a file (e.g., `image.jpg`) to the `c2pa-uploads-` GCS bucket.
2.  **Notify**: The multi-regional GCS bucket sends a notification of the new object to a central Pub/Sub topic.
3.  **Trigger**: This event triggers one of the regional Cloud Functions subscribed to the topic. Eventarc automatically routes the event to a function in an available region.
4.  **Process**: The Cloud Function executes and:
    a.  Downloads the uploaded file.
    b.  Fetches C2PA configuration (like author name) securely from **Secret Manager**.
    c.  Requests a short-lived signing certificate from the **Private CA Pool**.
    d.  Generates a C2PA manifest.
    e.  Signs the manifest using a multi-regional, hardware-backed key from **Cloud KMS**.
    f.  Embeds the signed manifest into the file.
5.  **Store**: The newly signed file (`image.jpg`) is uploaded to the `c2pa-signed-` GCS bucket.

## Prerequisites

Before you begin, ensure you have the following:

1.  **Google Cloud Project**: A GCP project with billing enabled. Note your **Project ID**.
2.  **Required Permissions**: The user or service account running Terraform will need significant permissions to create resources and set IAM policies. The `Owner` or `Editor` roles are sufficient for initial setup.
3.  **gcloud CLI**: The Google Cloud command-line tool installed and authenticated. Run the following commands to log in and set your project context:
    ```bash
    gcloud auth login
    gcloud auth application-default login
    gcloud config set project YOUR_PROJECT_ID
    ```
4.  **Terraform**: Terraform `~> 4.0` or newer installed on your local machine.

## Deployment Instructions

This project uses a two-stage process. First, we bootstrap the secure backend for Terraform's state. Second, we deploy the main application.

### Stage 1: Bootstrap the Backend (One-Time Setup)

This stage creates the GCS bucket where Terraform will securely store its state file and a Secret Manager secret to hold the bucket's name.

1.  **Navigate to the Bootstrap Directory**:
    ```bash
    cd bootstrap-backend
    ```

2.  **Set Project ID Environment Variable**:
    Terraform will automatically use this variable.
    *   For Linux/macOS:
        ```bash
        export TF_VAR_project_id="YOUR_PROJECT_ID"
        ```
    *   For Windows (PowerShell):
        ```powershell
        $env:TF_VAR_project_id="YOUR_PROJECT_ID"
        ```

3.  **Initialize and Apply Terraform**:
    This uses a local state file just for this one-time setup.
    ```bash
    terraform init
    terraform apply
    ```
    Review the plan and type `yes` to approve. This will create the state bucket and the secret.

### Stage 2: Deploy the C2PA Signing Service

Now we deploy the main application, which will use the backend you just created.

1.  **Navigate to the Main Project Directory**:
    ```bash
    cd ../c2pa-project
    ```

2.  **Run the Secure Initialization Script**:
    This script fetches the backend bucket name from Secret Manager and correctly initializes Terraform.

    **IMPORTANT**: You must run this script using `source` (or its shorthand `.`) so it can set the environment variables needed for the next step.

    ```bash
    source ./init.sh
    ```
    The script will detect your Project ID from your environment, ask for confirmation, and then run `terraform init` with the secure backend configuration.

3.  **(Optional) Customize the Configuration**:
    Create a file named `terraform.tfvars` to override default settings like the deployment regions or C2PA metadata.

    **File: `terraform.tfvars`**
    ```tfvars
    # Example: Deploy to three regions instead of the default two
    # regions = ["us-central1", "us-east1", "europe-west1"]

    # Example: Customize the C2PA manifest data
    # c2pa_claim_generator = "MyCompany-Media-Signer/3.0"
    # c2pa_author_name     = "My Awesome Company Inc."
    ```

4.  **Apply the Main Terraform Configuration**:
    Because the `init.sh` script set the `TF_VAR_project_id` environment variable, you can run `apply` without any arguments.

    ```bash
    terraform apply
    ```
    Review the extensive plan and type `yes` to deploy the entire signing service.

## How to Use the Service

1.  **Get the Upload Bucket Name**:
    Find the name of the input bucket from the Terraform output:
    ```bash
    # This command uses 'jq' to parse the output cleanly
    terraform output -json | jq -r .uploads_bucket_name.value
    ```

2.  **Upload a File**:
    Use the `gsutil` command to copy a local file to the upload bucket.
    ```bash
    # Example:
    gsutil cp path/to/my-image.jpg gs://c2pa-uploads-0a2952cf/
    ```

3.  **Verify the Signed File**:
    Within a minute, the signed version of the file will appear in the signed bucket. You can list its contents to verify:
    ```bash
    # Get the signed bucket name
    SIGNED_BUCKET=$(terraform output -json | jq -r .signed_bucket_name.value)

    # List the contents
    gsutil ls gs://${SIGNED_BUCKET}/
    ```

## Troubleshooting Common Errors

*   **`403: Cloud Resource Manager API has not been used...`**: This happens on new projects. Terraform needs this API to enable other APIs. Enable it manually once per project:
    ```bash
    gcloud services enable cloudresourcemanager.googleapis.com
    gcloud services enable serviceusage.googleapis.com
    ```

*   **`403: ...does not have permission to publish messages...`**: The GCS service account needs permission to send notifications to Pub/Sub. The Terraform code automatically adds this IAM binding, but if it fails, ensure the `google_pubsub_topic_iam_member.gcs_pubsub_publisher` resource is correctly configured.

*   **`403: ...does not have permission to write logs...`**: The Cloud Build service account needs permission to write logs. The Terraform code grants the `Logs Writer` role, but if you use a custom build account, you will need to grant this permission to it.

*   **`404: parent resource not found for caPools...`**: A race condition where a CA is created before its parent Pool is ready. The `depends_on` blocks in `cas.tf` are designed to prevent this.

*   **Persistent Provider/KMS Errors**: If you encounter strange `404` or routing errors after changing provider configurations, your local Terraform cache may be stale. A clean re-initialization usually fixes this:
    ```bash
    rm -rf .terraform
    rm -f .terraform.lock.hcl
    source ./init.sh
    terraform apply
    ```

## Cleanup

To avoid ongoing charges, you can destroy the infrastructure. This must also be done in two stages, in the reverse order of creation.

1.  **Destroy the Main Application**:
    ```bash
    cd c2pa-project
    terraform destroy
    ```

2.  **Destroy the Backend Resources**:
    ```bash
    cd ../bootstrap-backend
    terraform destroy
    ```
    **Note**: The state bucket has termination protection enabled. Terraform will show an error. To fully delete it, you must first edit `bootstrap-backend/main.tf`, change `prevent_destroy = true` to `false` for the `google_storage_bucket.tfstate` resource, and run `terraform apply` before running `terraform destroy`.
# c2pa-on-gcp
# A GCP-based C2PA Signing Service

This repository contains Terraform code to deploy a C2PA signing service on Google Cloud Platform.

## Prerequisites

1.  A GCP Project with billing enabled.
2.  The `gcloud` CLI installed and authenticated.
3.  Terraform installed.

## Deployment

1.  **Clone the repository:**

    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  **Create a `terraform.tfvars` file:**

    Create this file in the root of the repository and add your project ID:

    ```tfvars
    project_id = "your-gcp-project-id"
    ```

3.  **Initialize Terraform:**

    ```bash
    terraform init
    ```

4.  **Apply the Terraform configuration:**

    Review the plan and then apply it.

    ```bash
    terraform plan
    terraform apply
    ```

## How It Works

1.  Upload a file (e.g., a `.jpg` or `.mp4`) to the GCS bucket named `c2pa-uploads-<random_suffix>`.
2.  This will trigger the `c2pa-signer-function`.
3.  The function will generate a C2PA manifest, obtain a signing certificate, sign the manifest with a key from Cloud KMS, and embed it into the file.
4.  The newly signed file will be saved to the `c2pa-signed-<random_suffix>` bucket with the same name as the original.

## Important Notes

*   **C2PA Library**: The Python code in the Cloud Function uses a placeholder `c2pa` library. You will need to replace this with your actual C2PA-compliant library for manifest creation and embedding.
*   **Certificate Generation**: The `create_certificate` function in `main.py` is a placeholder. You'll need to implement the logic to create a proper Certificate Signing Request (CSR) and use the `google.cloud.privateca_v1` client to request a certificate from the CA pool.
*   **Security**: This example uses an HSM-backed key in Cloud KMS for high-assurance signing. Ensure that the IAM permissions are correctly configured and follow the principle of least privilege.
*   **Cost**: This deployment uses billable GCP services, including Cloud KMS, Certificate Authority Service (in 'DEVOPS' tier for cost-effectiveness), Cloud Functions, and GCS. Be sure to monitor your costs.

After deploying this infrastructure, you will have a robust and scalable solution for signing your content with C2PA metadata on GCP. Let me know if you have any questions or would like to explore any of these components in more detail.

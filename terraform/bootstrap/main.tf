###############################################################################
# Bootstrap — Run locally once to create the GCP project, state bucket, KMS,
# service accounts, and Workload Identity Federation.
#
# After this, the main terraform/ config uses the GCS backend and all future
# changes go through GitHub Actions.
#
# Usage:
#   cd terraform/bootstrap
#   terraform init
#   terraform apply
###############################################################################

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# GCP Project
# ---------------------------------------------------------------------------

resource "google_project" "this" {
  name            = "CaixaBank AI"
  project_id      = var.project_id
  org_id          = var.org_id
  billing_account = var.billing_account

  # Don't create the default VPC — we don't need compute networking
  auto_create_network = false
}

# ---------------------------------------------------------------------------
# API Enablement
# ---------------------------------------------------------------------------

locals {
  apis = [
    "storage.googleapis.com",
    "bigquery.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "cloudkms.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudtrace.googleapis.com",
    "billingbudgets.googleapis.com",
    "iamcredentials.googleapis.com",       # Required for Workload Identity Federation
    "sts.googleapis.com",                  # Required for Workload Identity Federation
    "cloudresourcemanager.googleapis.com", # Required for IAM policy reads
    "aiplatform.googleapis.com",           # Vertex AI scaffold (inactive by default)
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.apis)

  project = google_project.this.project_id
  service = each.value

  disable_dependent_services = false
  disable_on_destroy         = false
}

# ---------------------------------------------------------------------------
# Terraform State Bucket
#
# Stored in the same project we manage — not best practice, but acceptable
# without a dedicated admin project. The bucket has:
#   - Uniform bucket-level access (no ACLs, IAM-only)
#   - Versioning (recover from state corruption)
#   - Public access prevention enforced
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "tfstate" {
  name     = "${var.project_id}-tf-state"
  project  = google_project.this.project_id
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------------------
# Raw Data Bucket — for large CSVs that exceed dbt seed limits
#
# transactions_data.csv (1.2GB) and train_fraud_labels.json (152MB) are
# uploaded here, then loaded into BigQuery via bq load.
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "raw_data" {
  name     = "${var.project_id}-raw-data"
  project  = google_project.this.project_id
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------------------
# KMS — Keyring + Key for SOPS encryption of tfvars
# ---------------------------------------------------------------------------

resource "google_kms_key_ring" "sops" {
  name     = "sops-keyring"
  location = "global"
  project  = google_project.this.project_id

  depends_on = [google_project_service.apis]
}

resource "google_kms_crypto_key" "sops" {
  name     = "sops-key"
  key_ring = google_kms_key_ring.sops.id

  # 90-day automatic rotation
  rotation_period = "7776000s"

  lifecycle {
    prevent_destroy = true
  }
}

# ---------------------------------------------------------------------------
# Service Accounts
# ---------------------------------------------------------------------------

resource "google_service_account" "cloud_run" {
  account_id   = "cloud-run-sa"
  display_name = "Cloud Run runtime service account"
  project      = google_project.this.project_id

  depends_on = [google_project_service.apis]
}

resource "google_service_account" "github_actions" {
  account_id   = "github-actions-sa"
  display_name = "GitHub Actions via Workload Identity Federation"
  project      = google_project.this.project_id

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------------------
# Workload Identity Federation — GitHub Actions OIDC → GCP
#
# GitHub Actions authenticates via OIDC tokens. No service account keys
# are ever created or stored.
# ---------------------------------------------------------------------------

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  project                   = google_project.this.project_id

  depends_on = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC Provider"
  project                            = google_project.this.project_id

  # Only allow tokens from our specific repository
  attribute_condition = "assertion.repository == '${var.github_repo}'"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Allow the GitHub Actions WIF identity to impersonate the github-actions SA
resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# ---------------------------------------------------------------------------
# IAM — GitHub Actions SA permissions
# ---------------------------------------------------------------------------

locals {
  github_actions_roles = [
    "roles/storage.objectAdmin",         # Terraform state + raw data buckets
    "roles/artifactregistry.writer",     # Push Docker images
    "roles/run.admin",                   # Deploy Cloud Run services
    "roles/cloudkms.cryptoKeyDecrypter", # SOPS decrypt
    "roles/iam.serviceAccountUser",      # Act as cloud-run-sa for deployments
    "roles/viewer",                      # Read project resources for terraform plan
  ]
}

resource "google_project_iam_member" "github_actions" {
  for_each = toset(local.github_actions_roles)

  project = google_project.this.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# ---------------------------------------------------------------------------
# IAM — Cloud Run SA permissions
# ---------------------------------------------------------------------------

locals {
  cloud_run_roles = [
    "roles/bigquery.dataViewer", # Read BigQuery datasets
    "roles/bigquery.jobUser",    # Run BigQuery queries
    "roles/cloudtrace.agent",    # Send traces to Cloud Trace
    "roles/aiplatform.user",     # Vertex AI predictions (scaffold, inactive by default)
  ]
}

resource "google_project_iam_member" "cloud_run" {
  for_each = toset(local.cloud_run_roles)

  project = google_project.this.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

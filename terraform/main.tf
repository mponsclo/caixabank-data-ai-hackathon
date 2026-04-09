provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------

module "iam" {
  source     = "./modules/iam"
  project_id = var.project_id
}

module "kms" {
  source              = "./modules/kms"
  project_id          = var.project_id
  collaborator_emails = var.collaborator_emails
}

module "artifact_registry" {
  source     = "./modules/artifact_registry"
  project_id = var.project_id
  region     = var.region
}

module "bigquery" {
  source     = "./modules/bigquery"
  project_id = var.project_id
  region     = var.region
}

module "cloud_run" {
  source             = "./modules/cloud_run"
  project_id         = var.project_id
  region             = var.region
  cloud_run_sa_email = module.iam.cloud_run_sa_email
  image              = var.cloud_run_image
}

module "workload_identity" {
  source     = "./modules/workload_identity"
  project_id = var.project_id
}

# ---------------------------------------------------------------------------
# Budget Alert — protect the $300 free credit tier
#
# NOTE: The billing budgets API returns INVALID_ARGUMENT on free trial
# accounts. Set this up manually in the GCP Console:
#   Billing → Budgets & alerts → Create budget
#   Amount: $300, thresholds at 50%, 80%, 100%
# ---------------------------------------------------------------------------

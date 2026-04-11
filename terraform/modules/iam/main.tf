###############################################################################
# Service Accounts & IAM Role Bindings
#
# Service accounts are created in bootstrap (chicken-and-egg: WIF needs the SA
# to exist). This module imports them as data sources and manages role bindings
# that the main Terraform config controls.
###############################################################################

data "google_service_account" "cloud_run" {
  account_id = "cloud-run-sa"
  project    = var.project_id
}

data "google_service_account" "github_actions" {
  account_id = "github-actions-sa"
  project    = var.project_id
}

data "google_service_account" "pipeline" {
  account_id = "pipeline-sa"
  project    = var.project_id
}

# ---------------------------------------------------------------------------
# Cloud Run SA — runtime permissions
# ---------------------------------------------------------------------------

locals {
  cloud_run_roles = [
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
    "roles/cloudtrace.agent",
    "roles/aiplatform.user", # Vertex AI scaffold (inactive by default)
  ]
}

resource "google_project_iam_member" "cloud_run" {
  for_each = toset(local.cloud_run_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${data.google_service_account.cloud_run.email}"
}

# ---------------------------------------------------------------------------
# GitHub Actions SA — CI/CD permissions
# ---------------------------------------------------------------------------

locals {
  github_actions_roles = [
    "roles/storage.objectAdmin",
    "roles/artifactregistry.writer",
    "roles/run.admin",
    "roles/run.developer",
    "roles/cloudkms.cryptoKeyDecrypter",
    "roles/iam.serviceAccountUser",
    "roles/viewer",
  ]
}

resource "google_project_iam_member" "github_actions" {
  for_each = toset(local.github_actions_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${data.google_service_account.github_actions.email}"
}

# ---------------------------------------------------------------------------
# Pipeline SA — ingestion pipeline permissions
# ---------------------------------------------------------------------------

locals {
  pipeline_roles = [
    "roles/bigquery.dataEditor",    # Write to landing.transactions_data_stream
    "roles/bigquery.jobUser",       # Run streaming insert jobs
    "roles/pubsub.publisher",       # Publish messages to topic
    "roles/pubsub.subscriber",      # EventArc subscription
    "roles/run.invoker",            # Cloud Scheduler invokes producer; EventArc invokes consumer
    "roles/eventarc.eventReceiver", # Receive EventArc triggers
    "roles/storage.objectViewer",   # Read CSV + cursor from GCS
    "roles/storage.objectCreator",  # Write cursor to GCS
  ]
}

resource "google_project_iam_member" "pipeline" {
  for_each = toset(local.pipeline_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${data.google_service_account.pipeline.email}"
}

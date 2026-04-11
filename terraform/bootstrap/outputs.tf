output "project_id" {
  description = "GCP project ID"
  value       = google_project.this.project_id
}

output "project_number" {
  description = "GCP project number"
  value       = google_project.this.number
}

output "tfstate_bucket" {
  description = "GCS bucket for Terraform remote state"
  value       = google_storage_bucket.tfstate.name
}

output "raw_data_bucket" {
  description = "GCS bucket for raw data uploads (large CSVs)"
  value       = google_storage_bucket.raw_data.name
}

output "kms_key_id" {
  description = "KMS crypto key ID for SOPS configuration"
  value       = google_kms_crypto_key.sops.id
}

output "cloud_run_sa_email" {
  description = "Cloud Run service account email"
  value       = google_service_account.cloud_run.email
}

output "github_actions_sa_email" {
  description = "GitHub Actions service account email (set as GitHub secret GH_ACTIONS_SA_EMAIL)"
  value       = google_service_account.github_actions.email
}

output "pipeline_sa_email" {
  description = "Pipeline service account email (Cloud Functions)"
  value       = google_service_account.pipeline.email
}

output "functions_source_bucket" {
  description = "GCS bucket for Cloud Function source code archives"
  value       = google_storage_bucket.functions_source.name
}

output "wif_provider" {
  description = "Workload Identity Federation provider (set as GitHub secret WIF_PROVIDER)"
  value       = google_iam_workload_identity_pool_provider.github.name
}

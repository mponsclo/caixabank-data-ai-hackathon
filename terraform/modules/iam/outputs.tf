output "cloud_run_sa_email" {
  description = "Cloud Run service account email"
  value       = data.google_service_account.cloud_run.email
}

output "github_actions_sa_email" {
  description = "GitHub Actions service account email"
  value       = data.google_service_account.github_actions.email
}

output "pipeline_sa_email" {
  description = "Pipeline service account email (Cloud Functions)"
  value       = data.google_service_account.pipeline.email
}

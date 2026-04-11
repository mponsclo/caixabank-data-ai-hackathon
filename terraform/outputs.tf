output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "cloud_run_url" {
  description = "Cloud Run service URL"
  value       = module.cloud_run.service_url
}

output "artifact_registry_url" {
  description = "Artifact Registry repository URL"
  value       = module.artifact_registry.repository_url
}

output "bigquery_datasets" {
  description = "BigQuery dataset IDs by layer"
  value       = module.bigquery.dataset_ids
}

output "wif_provider" {
  description = "Workload Identity Federation provider (set as GitHub secret WIF_PROVIDER)"
  value       = module.workload_identity.provider_name
}

output "github_actions_sa_email" {
  description = "GitHub Actions SA email (set as GitHub secret GH_ACTIONS_SA_EMAIL)"
  value       = module.iam.github_actions_sa_email
}

output "producer_function_url" {
  description = "Producer Cloud Function URL (manual trigger: curl -X POST)"
  value       = module.cloud_functions.producer_url
}

output "pubsub_topic" {
  description = "Pub/Sub topic for transaction ingestion"
  value       = module.pubsub.topic_name
}

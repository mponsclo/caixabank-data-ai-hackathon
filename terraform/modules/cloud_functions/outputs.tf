output "producer_url" {
  description = "Producer Cloud Function URL (HTTP trigger)"
  value       = google_cloudfunctions2_function.producer.url
}

output "consumer_url" {
  description = "Consumer Cloud Function URL"
  value       = google_cloudfunctions2_function.consumer.url
}

output "scheduler_job_name" {
  description = "Cloud Scheduler job name"
  value       = google_cloud_scheduler_job.daily_ingestion.name
}

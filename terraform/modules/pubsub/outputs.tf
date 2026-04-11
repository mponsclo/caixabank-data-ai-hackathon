output "topic_name" {
  description = "Pub/Sub topic name for transaction ingestion"
  value       = google_pubsub_topic.transactions_ingestion.name
}

output "topic_id" {
  description = "Pub/Sub topic full resource ID"
  value       = google_pubsub_topic.transactions_ingestion.id
}

output "dlq_topic_name" {
  description = "Dead letter queue topic name"
  value       = google_pubsub_topic.transactions_ingestion_dlq.name
}

output "dlq_topic_id" {
  description = "Dead letter queue topic full resource ID"
  value       = google_pubsub_topic.transactions_ingestion_dlq.id
}

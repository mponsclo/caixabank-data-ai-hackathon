###############################################################################
# Pub/Sub — Transaction ingestion topic + dead letter queue
###############################################################################

resource "google_pubsub_topic" "transactions_ingestion" {
  name    = "transactions-ingestion"
  project = var.project_id

  # No retention — messages consumed immediately by push subscription
}

resource "google_pubsub_topic" "transactions_ingestion_dlq" {
  name    = "transactions-ingestion-dlq"
  project = var.project_id

  message_retention_duration = "604800s" # 7 days
}

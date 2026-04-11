variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "pipeline_sa_email" {
  description = "Service account email for Cloud Functions runtime identity"
  type        = string
}

variable "pubsub_topic_name" {
  description = "Pub/Sub topic name for transaction ingestion"
  type        = string
}

variable "source_bucket_name" {
  description = "GCS bucket for function source code archives"
  type        = string
}

variable "source_data_bucket" {
  description = "GCS bucket containing the transactions CSV"
  type        = string
}

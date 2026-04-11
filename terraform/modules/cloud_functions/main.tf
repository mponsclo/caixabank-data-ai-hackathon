###############################################################################
# Cloud Functions Gen2 — Producer (HTTP) + Consumer (EventArc/Pub/Sub)
# + Cloud Scheduler for automated ingestion
###############################################################################

data "google_project" "this" {
  project_id = var.project_id
}

# ---------------------------------------------------------------------------
# Source code packaging — zip function directories and upload to GCS
# ---------------------------------------------------------------------------

data "archive_file" "producer" {
  type        = "zip"
  source_dir  = "${path.module}/../../../functions/producer"
  output_path = "${path.module}/../../../.terraform-tmp/producer.zip"
}

data "archive_file" "consumer" {
  type        = "zip"
  source_dir  = "${path.module}/../../../functions/consumer"
  output_path = "${path.module}/../../../.terraform-tmp/consumer.zip"
}

resource "google_storage_bucket_object" "producer_source" {
  name   = "producer-${data.archive_file.producer.output_md5}.zip"
  bucket = var.source_bucket_name
  source = data.archive_file.producer.output_path
}

resource "google_storage_bucket_object" "consumer_source" {
  name   = "consumer-${data.archive_file.consumer.output_md5}.zip"
  bucket = var.source_bucket_name
  source = data.archive_file.consumer.output_path
}

# ---------------------------------------------------------------------------
# Producer — HTTP-triggered, called by Cloud Scheduler
#
# Reads next time-chunk of transactions from CSV in GCS, serializes as
# Protobuf, and publishes to Pub/Sub.
# ---------------------------------------------------------------------------

resource "google_cloudfunctions2_function" "producer" {
  name     = "txn-producer"
  location = var.region
  project  = var.project_id

  build_config {
    runtime     = "python312"
    entry_point = "produce"
    source {
      storage_source {
        bucket = var.source_bucket_name
        object = google_storage_bucket_object.producer_source.name
      }
    }
  }

  service_config {
    min_instance_count    = 0
    max_instance_count    = 1
    available_memory      = "512M" # CSV parsing needs memory
    timeout_seconds       = 300    # Large chunk reads take time
    service_account_email = var.pipeline_sa_email

    environment_variables = {
      GCP_PROJECT_ID  = var.project_id
      PUBSUB_TOPIC_ID = var.pubsub_topic_name
      SOURCE_BUCKET   = var.source_data_bucket
      SOURCE_FILE     = "transactions_data.csv"
      CURSOR_BUCKET   = var.source_data_bucket
      CURSOR_PATH     = "pipeline/cursor.json"
      CHUNK_DAYS      = "30"
    }
  }
}

# ---------------------------------------------------------------------------
# Consumer — EventArc Pub/Sub trigger
#
# Receives Protobuf messages from Pub/Sub, deserializes, and streams
# inserts to BigQuery landing.transactions_data_stream.
# ---------------------------------------------------------------------------

resource "google_cloudfunctions2_function" "consumer" {
  name     = "txn-consumer"
  location = var.region
  project  = var.project_id

  build_config {
    runtime     = "python312"
    entry_point = "consume"
    source {
      storage_source {
        bucket = var.source_bucket_name
        object = google_storage_bucket_object.consumer_source.name
      }
    }
  }

  service_config {
    min_instance_count    = 0
    max_instance_count    = 3
    available_memory      = "256M"
    timeout_seconds       = 60
    service_account_email = var.pipeline_sa_email

    environment_variables = {
      GCP_PROJECT_ID = var.project_id
      BQ_DATASET     = "landing"
      BQ_TABLE       = "transactions_data_stream"
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = "projects/${var.project_id}/topics/${var.pubsub_topic_name}"
    retry_policy   = "RETRY_POLICY_RETRY"

    service_account_email = var.pipeline_sa_email
  }
}

# ---------------------------------------------------------------------------
# Cloud Scheduler — triggers producer on a cron schedule
# ---------------------------------------------------------------------------

resource "google_cloud_scheduler_job" "daily_ingestion" {
  name      = "daily-transaction-ingestion"
  project   = var.project_id
  region    = var.region
  schedule  = "0 9 * * *" # Daily at 09:00 UTC
  time_zone = "UTC"

  http_target {
    uri         = google_cloudfunctions2_function.producer.url
    http_method = "POST"

    oidc_token {
      service_account_email = var.pipeline_sa_email
      audience              = google_cloudfunctions2_function.producer.url
    }
  }
}

# ---------------------------------------------------------------------------
# IAM — Pub/Sub service agent needs token creator for push to Gen2 functions
# ---------------------------------------------------------------------------

resource "google_project_iam_member" "pubsub_token_creator" {
  project = var.project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

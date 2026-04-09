output "dataset_ids" {
  description = "Map of dataset layer names to their IDs"
  value = {
    landing      = google_bigquery_dataset.landing.dataset_id
    logic        = google_bigquery_dataset.logic.dataset_id
    presentation = google_bigquery_dataset.presentation.dataset_id
  }
}

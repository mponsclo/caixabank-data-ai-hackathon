###############################################################################
# BigQuery Datasets — one per dbt layer (landing, logic, presentation)
#
# Storage billing model: LOGICAL
#
# Why not PHYSICAL for this project:
#   - Physical billing charges for active bytes (compressed) PLUS time-travel
#     (7 days) and fail-safe (7 days) storage, which adds ~30-40% overhead.
#   - At small data volumes (~13M transactions, well under 1 TB), that overhead
#     exceeds the savings from columnar compression.
#   - Physical billing only pays off at scale (multi-TB) where compression
#     ratios of 5-10x more than offset the time-travel/fail-safe surcharge.
#   - For a project on the free $300 credit tier, logical is the cheaper option.
#
# No table or partition expirations — this is historical banking transaction
# data that should be retained for the full analysis period.
###############################################################################

resource "google_bigquery_dataset" "landing" {
  dataset_id    = "landing"
  friendly_name = "Landing"
  description   = "Raw data — transactions (bq load from GCS), users/cards/MCC codes (dbt seeds)"
  project       = var.project_id
  location      = var.region

  storage_billing_model = "LOGICAL"
}

resource "google_bigquery_dataset" "logic" {
  dataset_id    = "logic"
  friendly_name = "Logic"
  description   = "Staged and enriched data — stg_transactions, stg_users, stg_cards, int_transactions_enriched, int_client_transactions"
  project       = var.project_id
  location      = var.region

  storage_billing_model = "LOGICAL"
}

resource "google_bigquery_dataset" "presentation" {
  dataset_id    = "presentation"
  friendly_name = "Presentation"
  description   = "ML-ready mart tables — mart_fraud_features (60+ cols), mart_client_monthly_expenses"
  project       = var.project_id
  location      = var.region

  storage_billing_model = "LOGICAL"
}

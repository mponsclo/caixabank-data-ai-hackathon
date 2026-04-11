# Data Transformation with dbt + BigQuery

Layered SQL transformations from raw CSVs to ML-ready feature tables.

## Why This Layer Exists

Raw transaction data is messy: amounts are strings with dollar signs, error codes are comma-separated text, boolean fields are `"YES"/"NO"` strings, and there's no feature engineering at all. Before any ML model can use this data, it needs to be cleaned, enriched with reference data, and transformed into meaningful features.

Instead of doing all of this in pandas (which would be a single monolithic script, hard to test, impossible to audit), the transformation layer uses **dbt on BigQuery**. Each transformation step is a SQL model with a clear purpose, documented columns, schema tests, and a lineage graph that shows exactly how data flows from raw to ML-ready.

The pipeline processes 13M transactions through three layers (staging → intermediate → marts) and produces 60+ fraud detection features, all computed in SQL via window functions.

## Data Model

The source data consists of three entities: users, transactions, and cards.

![Entity Relationship Diagram](data-model-erd.png)

Transactions reference both users (via `client_id`) and cards (via `card_id`). Each client can have multiple cards, and each card can have many transactions. The `mcc` field in transactions maps to a separate MCC codes reference table (not shown) that provides human-readable category names.

## Data Lineage

![dbt Lineage Graph](dbt-lineage.png)

The lineage graph above (from `dbt docs serve`) shows the full data flow. Sources and seeds on the left, staging views in the middle, and mart tables on the right. Every arrow is a dependency that dbt tracks and rebuilds automatically.

## Three-Layer Architecture

The pipeline follows the staging → intermediate → marts pattern across three BigQuery datasets:

| Layer | Dataset | Materialization | Purpose |
|-------|---------|----------------|---------|
| **Staging** | `landing` | Views | Clean, parse, normalize raw data |
| **Intermediate** | `logic` | Views | Join master data, derive base features |
| **Marts** | `presentation` | Tables | Final feature engineering for ML models |

A custom [`generate_schema_name`](../dbt/macros/generate_schema_name.sql) macro maps dbt's `+schema` config directly to BigQuery dataset names. Without it, dbt would generate compound names like `landing_staging` instead of just `landing`.

### A note on seeds vs sources

In this project, users, cards, and MCC codes are loaded as **dbt seeds** (small CSV files committed to the repo). The transactions table is loaded as a **source** via `bq load` from GCS because of its size (1.2GB).

In a production system, all of these would come from the landing tables populated by the [ingestion pipeline](1-ingestion.md). The seeds are a convenience for this project, but the staging SQL is written so that swapping `{{ ref('users_data') }}` for `{{ source('raw', 'users_data') }}` is a one-line change per model.

## Staging Layer

Four views that clean raw data without changing its grain (one row per source row):

### stg_transactions

The most important staging model. Transforms the raw `transactions_data` table:

- **Renames**: `id` → `transaction_id`, `date` → `transaction_date`
- **Parses error flags**: The raw `errors` column is a string (e.g., `"Bad CVV"`). The staging model parses it into 7 boolean columns using `IF()`:

```sql
IF(LOWER(COALESCE(errors, '')) LIKE '%bad cvv%', 1, 0) AS has_bad_cvv
```

This produces: `has_bad_cvv`, `has_bad_expiration`, `has_bad_card_number`, `has_bad_pin`, `has_insufficient_balance`, `has_technical_glitch`, `has_any_error`.

- **Derives channel**: `IF(use_chip = 'Online Transaction', 1, 0) AS is_online`
- **Casts types**: `SAFE_CAST(zip AS STRING)` for safe type conversion

### stg_users, stg_cards, stg_mcc_codes

Clean demographic and reference data: parse `$`-prefixed currency strings to FLOAT64 with `SAFE_CAST`, normalize boolean fields (`"YES"/"NO"` → BOOLEAN), extract dates from `MM/YYYY` strings.

## Intermediate Layer

Two views that enrich transactions with master data:

### int_transactions_enriched

Joins staging transactions with MCC category names into a single denormalized view. This is the foundation for both mart tables downstream.

### int_client_transactions

Extends `int_transactions_enriched` by joining client demographics (age, income, credit score, debt) and card attributes (chip, credit limit, card brand/type, expiry). Provides a complete view of each transaction with its user and card context.

## Marts Layer

### mart_fraud_features (60+ columns)

The centerpiece of the project: [`dbt/models/marts/mart_fraud_features.sql`](../dbt/models/marts/mart_fraud_features.sql). Computes 60+ features across 8 categories, all in SQL via window functions:

| Category | Count | Key Features | Why They Matter |
|----------|-------|-------------|----------------|
| **Amount** | 10 | `abs_amount`, `log_amount`, `amount_zscore`, `client_avg_amount_last50`, `amount_vs_client_max`, `above_client_p90`, `amount_to_limit_ratio` | Unusual amounts relative to client history signal fraud |
| **Time** | 5 | `txn_hour`, `txn_day_of_week`, `txn_month`, `txn_year`, `is_weekend` | Fraud clusters at unusual hours (3-5 AM) |
| **Errors** | 7 | `has_bad_cvv`, `has_bad_expiration`, `has_bad_pin`, `has_insufficient_balance`, `has_any_error`, `card_errors_7d` | Bad CVV = 23x base fraud rate (from EDA) |
| **Velocity** | 5 | `seconds_since_last_txn`, `card_txn_count_1h`, `card_txn_count_24h`, `card_txn_count_7d`, `card_amount_sum_24h` | Rapid successive transactions signal card testing |
| **Behavioral** | 7 | `card_mcc_freq`, `card_merchant_freq`, `card_distinct_mcc_7d`, `is_new_merchant`, `is_new_mcc`, `rapid_succession` | New merchant + new MCC = higher risk |
| **Geographic** | 2 | `is_online`, `is_out_of_home_state` | Online transactions = 28x fraud rate vs swipe (from EDA) |
| **Card/User** | 8 | `credit_limit`, `card_has_chip`, `card_age_months`, `credit_score`, `total_debt`, `yearly_income`, `debt_to_income_ratio` | Card age and credit profile correlate with fraud risk |
| **Combined Signals** | 4 | `online_new_merchant`, `online_high_amount`, `oos_new_merchant`, `error_online` | Interaction features that capture compound risk |

### mart_client_monthly_expenses

A simpler mart for expense forecasting (Task 4). Aggregates per client per month using `GROUP BY ALL`:

- `total_expenses` (sum of negative amounts)
- `total_earnings` (sum of positive amounts)
- `num_expense_transactions`, `avg_expense_amount`, `max_expense_amount`
- `total_transactions`

## Design Decisions

### Why BigQuery over DuckDB for production

The codebase has a **dual-path architecture**:

- **Production path**: dbt on BigQuery → `scripts/export_models.py` → `app/` (FastAPI on Cloud Run)
- **Hackathon path**: DuckDB local → `src/models/train_model.py` → `tests/`

BigQuery was chosen for production because it scales to billions of rows without memory concerns, integrates with the GCP ecosystem (Cloud Run, Cloud Functions, IAM), and dbt-bigquery handles schema management, incremental builds, and data tests. Window functions on 13M rows complete in seconds.

### LOGICAL billing model

BigQuery datasets use `LOGICAL` storage billing (not `PHYSICAL`). At small scale (<1TB), the time-travel and fail-safe overhead of PHYSICAL billing (~30-40%) exceeds compression savings. This is configured in the [BigQuery Terraform module](../terraform/modules/bigquery/main.tf).

### SQL style conventions

The SQL in this project follows a consistent style:

- **UPPER case** for all keywords (`SELECT`, `FROM`, `WHERE`, `IF`, `OVER`, etc.)
- **Leading commas** in SELECT lists (easier to comment out lines, cleaner diffs)
- **`WHERE TRUE`** followed by conditions on new lines (makes adding/removing filters trivial)
- **`GROUP BY ALL`** instead of listing columns explicitly
- **`IF()`** for two-outcome conditions, `CASE WHEN` only for 3+ branches
- **`COUNTIF()`**, **`SUM(IF())`** for conditional aggregation
- **`SAFE_CAST`** for user-facing data conversions
- **Named `WINDOW`** clauses to avoid repeating partition definitions
- **`QUALIFY`** to filter window function results without nesting

## Running dbt

> **Prerequisites:** You need a GCP project with BigQuery enabled and `gcloud auth application-default login` configured. See the [Infrastructure guide](7-infrastructure.md) for full setup.

```bash
# Full pipeline: seed reference data + run models + run tests
make dbt-build

# Individual steps
make dbt-seed    # Load seeds (users, cards, MCC codes) into landing
make dbt-run     # Run all models (staging → intermediate → marts)
make dbt-test    # Run schema tests

# Browse documentation with lineage graph
make dbt-docs    # http://localhost:8081

# Rebuild a single model
cd dbt && dbt run --select mart_fraud_features --profiles-dir .
```

All commands run from the `dbt/` directory with `--profiles-dir .` to use the local [`profiles.yml`](../dbt/profiles.yml).

## Scaling Considerations

This pipeline works well at 13M rows, but it would need significant redesign at petabyte scale:

**Incremental materialization.** The marts currently do full rebuilds on every `dbt run`. At scale, you would need incremental models that only process new rows. This is not trivial for window functions: features like `card_txn_count_24h` depend on a rolling window of historical data, so you can't just process the new rows in isolation. You'd need to recompute features for a trailing window around each new batch, which requires careful partition design and merge logic.

**Window function performance.** The `PARTITION BY card_id ORDER BY txn_epoch RANGE BETWEEN ...` patterns work fine on 13M rows (BigQuery handles them in seconds), but they become expensive at scale. Each window function scans the full partition for every row. At hundreds of millions of rows per card, you'd likely need to pre-aggregate into time buckets, use materialized views for rolling counts, or move velocity features to a feature store that computes them incrementally as events arrive.

**COUNT(DISTINCT) limitations.** BigQuery doesn't support `COUNT(DISTINCT)` as an analytic function. The current workaround (approximation via transaction counts) is honest but imprecise. At scale, you'd use `APPROX_COUNT_DISTINCT` (HyperLogLog) or compute exact distinct counts in a pre-aggregation step.

## Known Limitations

1. **`is_out_of_home_state` has mild leakage**: the client home state is computed from ALL transactions including future ones. Kept for consistency across experiments (documented in [experiments.md](8-experiments.md)).

2. **Seeds instead of landing tables**: users, cards, and MCC codes are loaded as dbt seeds rather than from the ingestion pipeline's landing tables. In production, these would come from the same Pub/Sub → BigQuery path described in the [ingestion guide](1-ingestion.md).

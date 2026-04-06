# CaixaBank Data AI Hackathon

> **Note:** This project was developed as part of a data science hackathon organized by NUWE in partnership with CaixaBank. The original datasets are not included in this repository as they may contain proprietary data. See [Data](#data) for details on the expected input format.

## Overview

End-to-end data science pipeline for banking transaction analysis: data engineering with **dbt + DuckDB**, fraud detection with **LightGBM + Focal Loss**, expense forecasting with **direct multi-step regression**, and an AI-powered report agent with **LangChain + Ollama**.

**Results:** 5/5 tasks complete, 9/9 tests pass.

| Task | Score Metric | Result |
|------|-------------|--------|
| 1. Data Queries | Exact match | 4/4 correct |
| 2. Data Functions | Pytest | 6/6 pass |
| 3. Fraud Detection | Balanced Accuracy | BA=0.97, AUPRC=0.61, F1=0.60 |
| 4. Expense Forecast | R2 Score | R2=0.76 (near theoretical ceiling) |
| 5. AI Agent | Pytest | 3/3 pass |

---

## Architecture

### Data Pipeline (dbt + DuckDB)

Instead of ad-hoc pandas preprocessing, the data layer uses a proper **dbt pipeline** with DuckDB as the warehouse — staging, intermediate, and mart layers with SQL-based transformations and schema tests.

```
data/raw/*.csv → [staging views] → [intermediate views] → [mart tables] → Python models
```

**Why dbt:** Reproducible transformations, testable SQL, self-documenting lineage. The `mart_fraud_features` table computes 60+ features (velocity, behavioral, error flags, geographic anomaly) entirely in SQL via window functions.

### Fraud Detection (Task 3)

**9 experiments** documented in [experiments.md](experiments.md), from a naive baseline (AUPRC≈0) to a production-grade model:

| Technique | Impact |
|-----------|--------|
| EDA-driven features (errors column, geographic anomaly) | AUPRC 0→0.43 |
| Out-of-fold target encoding (MCC, merchant_id) | AUPRC 0.43→0.49 |
| Focal loss (replaced scale_pos_weight) | AUPRC 0.49→0.57 |
| Card age, gap z-score, spending anomaly features | AUPRC 0.57→0.61 |

**Leakage caught:** Zip-based features inflated AUPRC to 0.89. Ablation study isolated the leak (client home zip computed from future data), features removed, honest metrics reported.

**Final model:** LightGBM + Focal Loss (gamma=2.0, alpha=0.25) + target encoding. Production operating point: 64% precision, 57% recall.

### Expense Forecast (Task 4)

Global LightGBM with **direct multi-step forecasting** (separate model per horizon h=1,2,3).

**Key finding:** 77% of variance is between-client (spending level), autocorrelation ≈ 0, no seasonality. R2=0.76 is near the theoretical ceiling (~0.80-0.84). Validated by testing 7 alternative approaches (blending, residual modeling, two-stage, EWMA) — all converge to ~0.76.

Walk-forward validated with 8 folds, reporting R2, MAE ($239), and RMSE ($314).

### AI Agent (Task 5)

Hybrid architecture: **LLM for date extraction** (ChatOllama with llama3.2:1b) + **deterministic pipeline** for client validation, data analysis, and PDF generation.

Regex fallback ensures reliability despite the small model's limitations. Handles ordinal months ("fourth month of 2017"), explicit ISO ranges, month names, and quarters.

---

## Data

The datasets are **not included** in this repository. To reproduce the results, you would need:

- `data/raw/transactions_data.csv` — Credit card transactions dataset (2010s decade) with columns: transaction ID, client ID, card ID, amount, merchant, MCC code, timestamps, errors, etc.
- `data/raw/mcc_codes.json` — Merchant Category Code mappings (109 categories).
- `data/raw/train_fraud_labels.json` — Binary fraud labels for training the detection model.
- Client and card data were fetched from APIs (no longer available) and stored as `clients_data_api.csv` and `card_data_api.csv`.

---

## How to Run

```bash
# Setup
source myenv/bin/activate

# Build dbt pipeline
cd dbt && dbt build --profiles-dir . && cd ..

# Train models
python src/models/train_model.py      # Fraud detection → predictions_3.json
python src/models/predict_model.py    # Expense forecast → predictions_4.json

# Run tests
python -m pytest tests/ -v            # 9/9 should pass
```

---

## Key Technical Decisions

1. **dbt over pandas for data prep** — SQL-based feature engineering is more maintainable and testable than pandas chains. Window functions for velocity/behavioral features are cleaner in SQL.

2. **Focal loss over class weights** — For 0.15% fraud rate, focal loss (gamma=2.0) outperformed scale_pos_weight tuning by focusing gradient updates on hard-to-classify examples.

3. **Direct over recursive forecasting** — Three separate horizon models avoid error propagation. Since autocorrelation ≈ 0, there's no temporal structure for recursive to exploit.

4. **Regex fallback for LLM** — llama3.2:1b is unreliable for structured output. The hybrid approach satisfies the hackathon's LangChain requirement while guaranteeing deterministic test results.

5. **Parameterized SQL everywhere** — `con.execute(query, [params])` instead of f-strings to prevent SQL injection.

---

## Repository Structure

```
├── data/                      # Not included (gitignored)
│   ├── raw/                   # Source CSV/JSON files
│   ├── processed/             # Legacy preprocessed files
│   └── dbt_output/            # DuckDB database from dbt
├── dbt/                       # dbt-duckdb data pipeline
│   ├── models/
│   │   ├── staging/           # 4 views: stg_transactions, stg_users, stg_cards, stg_mcc_codes
│   │   ├── intermediate/      # 2 views: int_transactions_enriched, int_client_transactions
│   │   └── marts/             # 2 tables: mart_fraud_features, mart_client_monthly_expenses
│   ├── seeds/                 # mcc_codes.csv
│   └── profiles.yml           # DuckDB connection config
├── predictions/               # JSON outputs for Tasks 1, 3, 4
├── src/
│   ├── data/                  # Task 1 queries, Task 2 functions, API calls, preprocessing
│   ├── models/                # Task 3 fraud model, Task 4 forecast model
│   └── agent/                 # Task 5 AI agent
├── tests/                     # Test suite
├── experiments.md             # Full experiment log (11 experiments)
└── reports/figures/           # Generated plots
```

## Experiment Tracking

Full experiment logs with metrics, ablation studies, and root cause analysis are in [experiments.md](experiments.md) — 11 experiments total across fraud detection and expense forecasting.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

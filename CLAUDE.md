# CLAUDE.md

## Project Overview

CaixaBank Data AI Hackathon — a 5-task data science challenge working with banking transaction data.

**Stack:** Python 3.10 + dbt-duckdb + LightGBM + LangChain

## Quick Start

```bash
# Activate virtual environment
source myenv/bin/activate

# Run dbt pipeline (from dbt/ directory)
cd dbt && dbt build --profiles-dir . && cd ..

# Run tests
python -m pytest tests/statistics_test.py -v    # Task 2
python -m pytest tests/agent_test.py -v          # Task 5

# Train models
python src/models/train_model.py                 # Task 3: Fraud detection
python src/models/predict_model.py               # Task 4: Expense forecast
```

## Repository Structure

```
├── data/
│   ├── raw/               # Source CSV/JSON files (gitignored)
│   ├── processed/         # Legacy preprocessed files
│   └── dbt_output/        # DuckDB database from dbt (gitignored)
├── dbt/                   # dbt-duckdb data pipeline
│   ├── models/
│   │   ├── staging/       # 4 views: stg_transactions, stg_users, stg_cards, stg_mcc_codes
│   │   ├── intermediate/  # 2 views: int_transactions_enriched, int_client_transactions
│   │   └── marts/         # 2 tables: mart_fraud_features (60+ cols), mart_client_monthly_expenses
│   ├── seeds/             # mcc_codes.csv (109 merchant categories)
│   └── profiles.yml       # DuckDB connection config
├── predictions/           # JSON outputs for Tasks 1, 3, 4
├── src/
│   ├── data/              # Task 1 queries, Task 2 functions, API calls, preprocessing
│   ├── models/            # Task 3 fraud model, Task 4 forecast model
│   └── agent/             # Task 5 AI agent
├── tests/                 # Hackathon-provided test suite
├── experiments.md         # Full experiment log (9 fraud experiments, 2 forecast experiments)
└── reports/figures/       # Generated plots from Task 2 functions
```

## Task Status

| Task | Status | Score Metric | Result |
|------|--------|-------------|--------|
| 1. Data Queries | DONE | Exact match | predictions_1.json submitted |
| 2. Data Functions | DONE | Pytest | 6/6 tests pass |
| 3. Fraud Detection | DONE | Balanced Accuracy | BA=0.97, AUPRC=0.61 |
| 4. Expense Forecast | DONE | R2 Score | R2=0.76 (walk-forward validated) |
| 5. AI Agent | DONE | Pytest | 3/3 tests pass |

## Key Architecture Decisions

### dbt Pipeline
- **Why dbt+DuckDB:** Portfolio showcase — proper staging/intermediate/mart layers with SQL-based feature engineering, schema tests, and documentation.
- **mart_fraud_features:** 60+ features including velocity (txn counts in rolling windows), behavioral (merchant/MCC frequency), error flags (Bad CVV = 23x fraud rate), geographic anomaly, card age, inter-purchase gap z-scores.
- **mart_client_monthly_expenses:** Monthly aggregation per client for expense forecasting.

### Fraud Detection (Task 3)
- **Model:** LightGBM + Focal Loss (gamma=2.0, alpha=0.25) + Out-of-fold Target Encoding on MCC and merchant_id.
- **Key insight:** Focal loss replaced scale_pos_weight tuning. Target encoding turned noisy categoricals into fraud-rate signals. EDA-driven features (errors column, geographic anomaly) mattered more than model tuning.
- **Leakage caught:** Zip-based features caused AUPRC to jump from 0.57 to 0.89 — ablation study revealed the `client_home_zip` CTE used future data. Features removed, honest AUPRC = 0.61.
- **Experiments logged in `experiments.md`** (9 experiments from baseline to final model).

### Expense Forecast (Task 4)
- **Model:** Global LightGBM with direct multi-step forecasting (one model per horizon h=1,2,3).
- **Key insight:** 77% of variance is between-client (spending level). Autocorrelation ≈ 0. No seasonality. R2=0.76 is near the theoretical ceiling (~0.80-0.84) for this data. Validated via 8-fold walk-forward with MAE/RMSE/R2.
- **7 alternative approaches tested** (all converge to ~0.76): blending, residual modeling, two-stage, EWMA, Huber loss.

### AI Agent (Task 5)
- **Architecture:** Hybrid LLM + deterministic pipeline. LLM (llama3.2:1b via Ollama) extracts dates from natural language, with regex fallback for reliability. Client validation, function calls, and PDF generation are all deterministic.
- **Date parsing:** Few-shot prompt → JSON extraction → regex fallback. Handles ordinal months ("fourth month"), ISO ranges, month names, quarters.
- **PDF generation:** fpdf2 multi-page report with tables from all 3 Task 2 functions + embedded chart PNGs.
- **Robustness:** Works even without Ollama running (regex fallback catches all test patterns).

### Data Functions (Task 2)
- **Parameterized SQL:** Uses `duckdb.execute()` with `$1/$2/$3` placeholders (no SQL injection).
- **Each function creates/closes its own DuckDB connection** — no module-level side effects.

## Code Conventions

- SQL queries use parameterized execution (`con.execute(query, [params])`) not f-strings
- DuckDB connections are always explicitly closed
- All functions have docstrings (NumPy style for public API)
- `__init__.py` in all Python packages
- Features computed with `shift(1)` or `shift(lag)` to avoid temporal leakage
- Walk-forward validation for all time-series models

## Known Limitations

- `is_out_of_home_state` feature has mild leakage (client home state computed from ALL transactions including future). Kept for consistency across experiments.
- `data_preprocessing.py` and `api_calls.py` are pre-existing legacy code not refactored.
- The `dbt/` directory CSV paths are relative to the dbt project root — run dbt commands from `dbt/` directory.

## Running dbt

```bash
cd dbt
dbt debug --profiles-dir .       # verify connection
dbt build --profiles-dir .       # seed + models + tests
dbt run --select mart_fraud_features --profiles-dir .  # rebuild single model
```

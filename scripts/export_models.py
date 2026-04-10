"""
Export trained models to pkl files for the FastAPI serving layer.

Trains fraud detection + 3 forecast horizon models, then serializes:
  - outputs/models/fraud_model.pkl (LightGBM booster)
  - outputs/models/forecast_h1.pkl, forecast_h2.pkl, forecast_h3.pkl
  - outputs/models/target_encodings.pkl (MCC + merchant_id mappings)
  - outputs/models/feature_metadata.pkl (feature lists + client features)

Usage:
    python scripts/export_models.py
"""

import os
import sys

import joblib
import lightgbm as lgb
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.predict_model import build_features
from src.models.train_model import (
    CATEGORICAL_COLS,
    FEATURE_COLS,
    TE_ALPHA,
    TE_COLS,
    focal_loss_eval,
    focal_loss_objective,
    load_labels,
    prepare_features,
)

OUTPUT_DIR = "outputs/models"
# Use BigQuery client if available, fall back to DuckDB for local dev
BQ_PROJECT = os.environ.get("GCP_PROJECT_ID", "mpc-caixabank-ai")


def _load_fraud_data_bigquery():
    """Load fraud features from BigQuery."""
    from google.cloud import bigquery

    client = bigquery.Client(project=BQ_PROJECT)
    query = f"SELECT * FROM `{BQ_PROJECT}.presentation.mart_fraud_features`"
    return client.query(query).to_dataframe()


def _load_fraud_data_duckdb():
    """Load fraud features from local DuckDB (fallback)."""
    import duckdb

    con = duckdb.connect("data/dbt_output/caixabank.duckdb", read_only=True)
    df = con.sql("SELECT * FROM mart_fraud_features").df()
    con.close()
    return df


def _load_monthly_data_bigquery():
    """Load monthly expenses from BigQuery."""
    from google.cloud import bigquery

    client = bigquery.Client(project=BQ_PROJECT)
    query = f"SELECT * FROM `{BQ_PROJECT}.presentation.mart_client_monthly_expenses`"
    df = client.query(query).to_dataframe()
    df["expense_month"] = pd.to_datetime(df["expense_month"])
    return df


def _load_monthly_data_duckdb():
    """Load monthly expenses from local DuckDB (fallback)."""
    import duckdb

    con = duckdb.connect("data/dbt_output/caixabank.duckdb", read_only=True)
    df = con.sql("SELECT * FROM mart_client_monthly_expenses").df()
    con.close()
    df["expense_month"] = pd.to_datetime(df["expense_month"])
    return df


def export_fraud_model():
    """Train and export fraud detection model."""
    print("=== Exporting Fraud Detection Model ===")

    # Load data
    try:
        features_df = _load_fraud_data_bigquery()
        print("Loaded from BigQuery")
    except Exception:
        features_df = _load_fraud_data_duckdb()
        print("Loaded from DuckDB (local fallback)")

    labels = load_labels()
    features_df["is_fraud"] = features_df["transaction_id"].map(labels)
    train_df = features_df[features_df["is_fraud"].notna()].copy()
    train_df["is_fraud"] = train_df["is_fraud"].astype(int)

    # Target encoding
    te_mappings = {}
    for col in TE_COLS:
        global_mean = train_df["is_fraud"].mean()
        stats = train_df.groupby(col)["is_fraud"].agg(["sum", "count"])
        stats["encoded"] = (stats["sum"] + TE_ALPHA * global_mean) / (stats["count"] + TE_ALPHA)
        mapping = stats["encoded"].to_dict()
        mapping["__global_mean__"] = global_mean
        te_mappings[col] = mapping
        train_df[f"{col}_te"] = (
            train_df[col].map({k: v for k, v in mapping.items() if k != "__global_mean__"}).fillna(global_mean)
        )

    train_df = prepare_features(train_df)

    X = train_df[FEATURE_COLS]
    y = train_df["is_fraud"]

    # Train final model on all labeled data
    params = {
        "n_estimators": 1000,
        "learning_rate": 0.05,
        "max_depth": 6,
        "num_leaves": 63,
        "min_child_samples": 300,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.5,
        "reg_lambda": 2.0,
        "random_state": 42,
        "verbose": -1,
    }
    model = lgb.LGBMClassifier(
        objective=focal_loss_objective,
        **params,
    )
    model.fit(
        X,
        y,
        categorical_feature=CATEGORICAL_COLS,
        eval_metric=focal_loss_eval,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    joblib.dump(model, os.path.join(OUTPUT_DIR, "fraud_model.pkl"))
    joblib.dump(te_mappings, os.path.join(OUTPUT_DIR, "target_encodings.pkl"))
    print(f"Fraud model saved ({len(FEATURE_COLS)} features)")
    return te_mappings


def export_forecast_models():
    """Train and export 3 forecast horizon models."""
    print("\n=== Exporting Forecast Models ===")

    try:
        monthly_df = _load_monthly_data_bigquery()
        print("Loaded from BigQuery")
    except Exception:
        monthly_df = _load_monthly_data_duckdb()
        print("Loaded from DuckDB (local fallback)")

    # Load demographics
    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=BQ_PROJECT)
        demo_df = client.query(f"SELECT * FROM `{BQ_PROJECT}.landing.users_data`").to_dataframe()
    except Exception:
        demo_df = pd.read_csv("data/raw/users_data.csv")
        demo_df = demo_df.rename(columns={"id": "client_id"})
        for col in ["per_capita_income", "yearly_income", "total_debt"]:
            if col in demo_df.columns and demo_df[col].dtype == object:
                demo_df[col] = demo_df[col].str.replace(r"[\$,]", "", regex=True).astype(float)

    # Ensure demo_df has the expected column names
    if "id" in demo_df.columns and "client_id" not in demo_df.columns:
        demo_df = demo_df.rename(columns={"id": "client_id"})

    features_df = build_features(monthly_df, demo_df)

    # Train 3 models (h=1, h=2, h=3)
    # Exclude non-numeric columns (strings from demographics join)
    exclude_cols = {
        "client_id",
        "expense_month",
        "total_expenses",
        "target_h1",
        "target_h2",
        "target_h3",
    }
    feature_cols = [
        c
        for c in features_df.columns
        if c not in exclude_cols
        and features_df[c].dtype in ["float64", "float32", "int64", "int32", "bool", "Float64", "Int64"]
    ]

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for h in [1, 2, 3]:
        target_col = f"target_h{h}"
        if target_col not in features_df.columns:
            features_df[target_col] = features_df.groupby("client_id")["total_expenses"].shift(-h)

        train_data = features_df.dropna(subset=[target_col])
        X = train_data[feature_cols].fillna(0)
        y = train_data[target_col]

        model = lgb.LGBMRegressor(
            n_estimators=500,
            learning_rate=0.03,
            max_depth=6,
            num_leaves=31,
            min_child_samples=30,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.5,
            reg_lambda=2.0,
            random_state=42,
            verbose=-1,
        )
        model.fit(X, y)
        joblib.dump(model, os.path.join(OUTPUT_DIR, f"forecast_h{h}.pkl"))
        print(f"Forecast h={h} model saved ({len(feature_cols)} features)")

    # Save client features for the last available month (for API predictions)
    last_month = features_df.groupby("client_id").tail(1)
    client_features = {}
    for _, row in last_month.iterrows():
        client_features[int(row["client_id"])] = {
            col: float(row[col]) if pd.notna(row[col]) else 0.0 for col in feature_cols
        }

    return feature_cols, client_features


def main():
    export_fraud_model()
    forecast_features, client_features = export_forecast_models()

    # Save feature metadata
    metadata = {
        "fraud_features": FEATURE_COLS,
        "forecast_features": forecast_features,
        "client_features": client_features,
    }
    joblib.dump(metadata, os.path.join(OUTPUT_DIR, "feature_metadata.pkl"))
    print(f"\nFeature metadata saved ({len(client_features)} clients)")
    print(f"\nAll models exported to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()

"""
Task 4: Monthly Expense Forecasting

Predicts the next 3 months of total expenses per client using a global
LightGBM model with proper direct multi-step forecasting.

Key findings from EDA:
- 77% of variance is between-client (spending level)
- Zero autocorrelation — no seasonal patterns in this data
- 57% of clients are volatile (CV > 0.7)
- 78% of clients have zero-expense months
- YoY correlation is ~0 — same_month_last_year is useless

Architecture:
- 3 separate LightGBM models (h=1, h=2, h=3) with properly shifted targets
- Each model trained on (features_at_time_t, expense_at_time_t+h) pairs
- Features: lags, rolling stats, earnings context, demographics
- No seasonal features (EDA showed zero seasonality)
"""

import json
import duckdb
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error


DB_PATH = "data/dbt_output/caixabank.duckdb"
PREDICTIONS_PATH = "predictions/predictions_4.json"


# ---------- Data Loading ----------

def load_monthly_expenses():
    """Load monthly expense aggregations from dbt mart."""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.sql("""
        SELECT
            client_id, expense_month, total_expenses,
            num_expense_transactions, avg_expense_amount, max_expense_amount,
            total_earnings, total_transactions
        FROM mart_client_monthly_expenses
        ORDER BY client_id, expense_month
    """).df()
    con.close()
    df["expense_month"] = pd.to_datetime(df["expense_month"])
    return df


def load_client_demographics():
    """Load client demographic features from raw users CSV."""
    con = duckdb.connect()
    df = con.sql("""
        SELECT
            id as client_id, current_age, credit_score,
            REPLACE(REPLACE(yearly_income, '$', ''), ',', '')::DOUBLE as yearly_income,
            REPLACE(REPLACE(total_debt, '$', ''), ',', '')::DOUBLE as total_debt,
            num_credit_cards,
            CASE WHEN REPLACE(REPLACE(yearly_income, '$', ''), ',', '')::DOUBLE > 0
                 THEN REPLACE(REPLACE(total_debt, '$', ''), ',', '')::DOUBLE
                      / REPLACE(REPLACE(yearly_income, '$', ''), ',', '')::DOUBLE
                 ELSE 0 END as debt_to_income
        FROM read_csv_auto('data/raw/users_data.csv')
    """).df()
    con.close()
    return df


def load_prediction_targets():
    """Load target months per client from predictions_4.json."""
    with open(PREDICTIONS_PATH) as f:
        data = json.load(f)
    return {int(cid): sorted(months.keys()) for cid, months in data["target"].items()}


# ---------- Feature Engineering ----------

def build_features(monthly_df, demographics_df):
    """Build features for each client-month row.

    All features use only past data (shift(1) or shift(lag)) to avoid leakage.
    """
    df = monthly_df.copy().sort_values(["client_id", "expense_month"]).reset_index(drop=True)

    g = df.groupby("client_id")["total_expenses"]

    # Lag features
    for lag in [1, 2, 3, 6, 12]:
        df[f"lag_{lag}"] = g.shift(lag)

    # Rolling statistics (shifted by 1 to avoid leakage)
    for window in [3, 6, 12]:
        df[f"rmean_{window}"] = g.transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).mean()
        )
        df[f"rstd_{window}"] = g.transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).std()
        )

    df["rmedian_6"] = g.transform(lambda x: x.shift(1).rolling(6, min_periods=1).median())
    df["rmin_6"] = g.transform(lambda x: x.shift(1).rolling(6, min_periods=1).min())
    df["rmax_6"] = g.transform(lambda x: x.shift(1).rolling(6, min_periods=1).max())

    # Trend: short vs long term spending direction
    df["trend_3v12"] = (df["rmean_3"] - df["rmean_12"]) / df["rmean_12"].clip(lower=1)
    df["trend_3v6"] = (df["rmean_3"] - df["rmean_6"]) / df["rmean_6"].clip(lower=1)

    # Momentum: recent change
    df["momentum_1"] = df["lag_1"] - df["lag_2"]
    df["momentum_3"] = df["lag_1"] - df["lag_3"]

    # Volatility
    df["cv_12"] = df["rstd_12"] / df["rmean_12"].clip(lower=1)
    df["cv_6"] = df["rstd_6"] / df["rmean_6"].clip(lower=1)

    # Zero-expense frequency in recent history
    df["zero_freq_6m"] = df.groupby("client_id")["total_expenses"].transform(
        lambda x: x.shift(1).rolling(6, min_periods=1).apply(lambda w: (w == 0).mean())
    )

    # Earnings context
    eg = df.groupby("client_id")["total_earnings"]
    df["earn_lag1"] = eg.shift(1)
    df["earn_rmean_3"] = eg.transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    df["earn_expense_ratio"] = df["earn_lag1"] / df["lag_1"].clip(lower=1)

    # Transaction frequency
    tg = df.groupby("client_id")["num_expense_transactions"]
    df["txn_lag1"] = tg.shift(1)
    df["txn_rmean_3"] = tg.transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())

    # Avg expense per transaction (spending intensity)
    df["avg_expense_lag1"] = df.groupby("client_id")["avg_expense_amount"].shift(1)

    # Max expense spike: ratio of max single expense to rolling mean
    df["max_ratio"] = df.groupby("client_id")["max_expense_amount"].shift(1) / df["rmean_6"].clip(lower=1)

    # Range of recent spending (max - min over 6 months)
    df["range_6"] = df["rmax_6"] - df["rmin_6"]

    # Demographics
    df = df.merge(demographics_df, on="client_id", how="left")

    # Month of year (keep for potential weak seasonality in some clients)
    df["month_of_year"] = df["expense_month"].dt.month

    return df


FEATURE_COLS = [
    # Lags
    "lag_1", "lag_2", "lag_3", "lag_6", "lag_12",
    # Rolling stats
    "rmean_3", "rmean_6", "rmean_12",
    "rstd_3", "rstd_6", "rstd_12",
    "rmedian_6", "rmin_6", "rmax_6",
    # Trend/momentum
    "trend_3v12", "trend_3v6", "momentum_1", "momentum_3",
    # Volatility
    "cv_12", "cv_6",
    # Zero-expense frequency
    "zero_freq_6m",
    # Earnings
    "earn_lag1", "earn_rmean_3", "earn_expense_ratio",
    # Transactions
    "txn_lag1", "txn_rmean_3", "avg_expense_lag1",
    # Spike/range
    "max_ratio", "range_6",
    # Demographics
    "current_age", "credit_score", "yearly_income",
    "total_debt", "num_credit_cards", "debt_to_income",
    # Calendar
    "month_of_year",
]


# ---------- Direct Multi-Step Training ----------

def build_direct_targets(featured_df):
    """Build target columns for h=1, h=2, h=3 direct forecasting.

    For each row at time t, target_h is the expense at time t+h.
    """
    df = featured_df.copy()
    g = df.groupby("client_id")["total_expenses"]
    for h in [1, 2, 3]:
        df[f"target_h{h}"] = g.shift(-h)
    return df


# ---------- Validation ----------

def walk_forward_validate(featured_df, n_val_months=8):
    """Walk-forward validation with proper direct targets and multiple metrics."""
    df = build_direct_targets(featured_df)
    df = df.dropna(subset=["lag_12"]).copy()

    max_month = df["expense_month"].max()
    val_months = pd.date_range(end=max_month - pd.DateOffset(months=3), periods=n_val_months, freq="MS")

    results = {h: {"r2": [], "mae": [], "rmse": []} for h in [1, 2, 3]}

    for val_month in val_months:
        for h in [1, 2, 3]:
            # Train on data where we know the target (expense at t+h)
            train_mask = (df["expense_month"] < val_month) & df[f"target_h{h}"].notna()
            val_mask = (df["expense_month"] == val_month) & df[f"target_h{h}"].notna()

            train = df[train_mask]
            val = df[val_mask]

            if len(val) < 10 or len(train) < 100:
                continue

            X_train = train[FEATURE_COLS].fillna(0)
            y_train = train[f"target_h{h}"]
            X_val = val[FEATURE_COLS].fillna(0)
            y_val = val[f"target_h{h}"]

            model = lgb.LGBMRegressor(
                n_estimators=500, learning_rate=0.03, max_depth=6,
                num_leaves=31, min_child_samples=30, subsample=0.8,
                colsample_bytree=0.8, reg_alpha=0.5, reg_lambda=2.0,
                random_state=42, n_jobs=-1, verbose=-1,
            )
            model.fit(X_train, y_train)
            preds = np.maximum(model.predict(X_val), 0)

            results[h]["r2"].append(r2_score(y_val, preds))
            results[h]["mae"].append(mean_absolute_error(y_val, preds))
            results[h]["rmse"].append(np.sqrt(mean_squared_error(y_val, preds)))

    print("\n--- Walk-Forward Validation (Direct Multi-Step) ---")
    print(f"{'Horizon':<10s} {'R2':>8s} {'MAE ($)':>10s} {'RMSE ($)':>10s}")
    print("-" * 40)
    for h in [1, 2, 3]:
        r = results[h]
        if r["r2"]:
            print(f"  h={h:<6d} {np.mean(r['r2']):>8.4f} {np.mean(r['mae']):>10.2f} {np.mean(r['rmse']):>10.2f}")

    all_r2 = [s for h in [1, 2, 3] for s in results[h]["r2"]]
    all_mae = [s for h in [1, 2, 3] for s in results[h]["mae"]]
    avg_r2 = np.mean(all_r2) if all_r2 else 0
    print(f"  {'Overall':<8s} {avg_r2:>8.4f} {np.mean(all_mae):>10.2f}")

    return avg_r2


# ---------- Training & Prediction ----------

def train_and_predict():
    """Train expense forecast models and write predictions to predictions_4.json."""
    print("Loading data...")
    monthly_df = load_monthly_expenses()
    demographics = load_client_demographics()
    targets = load_prediction_targets()

    print(f"Clients: {monthly_df['client_id'].nunique()}")
    print(f"Monthly records: {len(monthly_df):,}")
    print(f"Prediction targets: {len(targets)} clients")

    print("\nBuilding features...")
    featured_df = build_features(monthly_df, demographics)

    # Validation
    val_r2 = walk_forward_validate(featured_df)

    # Build direct targets for final training
    df_with_targets = build_direct_targets(featured_df)
    train_data = df_with_targets.dropna(subset=["lag_12"]).copy()

    # Train one model per horizon
    print("\n--- Training Final Models (Direct h=1,2,3) ---")
    models = {}
    for h in [1, 2, 3]:
        h_data = train_data[train_data[f"target_h{h}"].notna()]
        X = h_data[FEATURE_COLS].fillna(0)
        y = h_data[f"target_h{h}"]

        model = lgb.LGBMRegressor(
            n_estimators=500, learning_rate=0.03, max_depth=6,
            num_leaves=31, min_child_samples=30, subsample=0.8,
            colsample_bytree=0.8, reg_alpha=0.5, reg_lambda=2.0,
            random_state=42, n_jobs=-1, verbose=-1,
        )
        model.fit(X, y)
        models[h] = model
        print(f"  h={h}: trained on {len(X):,} samples")

    # Feature importance (h=1)
    importance = sorted(
        zip(FEATURE_COLS, models[1].feature_importances_),
        key=lambda x: x[1], reverse=True,
    )
    print("\nTop 15 features (h=1):")
    for feat, imp in importance[:15]:
        print(f"  {feat:25s} {imp}")

    # Generate predictions
    print("\n--- Generating Predictions ---")
    with open(PREDICTIONS_PATH) as f:
        output = json.load(f)

    for cid_str, month_dict in output["target"].items():
        cid = int(cid_str)
        target_months = sorted(month_dict.keys())

        client_history = featured_df[featured_df["client_id"] == cid].sort_values("expense_month")
        if client_history.empty:
            continue

        last_row = client_history.iloc[-1]

        for i, month_str in enumerate(target_months):
            h = i + 1

            # Build features for this prediction
            feat_dict = {c: last_row.get(c, 0) for c in FEATURE_COLS}

            # Update calendar
            target_date = pd.Timestamp(month_str + "-01")
            feat_dict["month_of_year"] = target_date.month

            features = pd.DataFrame([feat_dict])[FEATURE_COLS].fillna(0)
            pred = max(0, float(models[h].predict(features)[0]))
            month_dict[month_str] = round(pred, 2)

    with open(PREDICTIONS_PATH, "w") as f:
        json.dump(output, f)

    all_preds = [v for md in output["target"].values() for v in md.values()]
    print(f"\nPredictions written to {PREDICTIONS_PATH}")
    print(f"Total: {len(all_preds)}, Mean: ${np.mean(all_preds):,.2f}, "
          f"Median: ${np.median(all_preds):,.2f}")
    print(f"Validation R2: {val_r2:.4f}")

    return val_r2


if __name__ == "__main__":
    train_and_predict()

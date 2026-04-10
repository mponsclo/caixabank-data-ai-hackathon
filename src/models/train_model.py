"""
Task 3: Fraud Detection Model

Iterative fraud detection pipeline:
- Exp 1-4: Feature engineering, EDA-driven features, SPW calibration
- Exp 5: Target encoding (MCC, merchant_id) + extra features
- Exp 6: Focal loss + hyperparameter tuning
- Exp 7: Ensemble stacking (LightGBM + XGBoost) + calibration
"""

import json

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import KFold

DB_PATH = "data/dbt_output/caixabank.duckdb"
LABELS_PATH = "data/raw/train_fraud_labels.json"
PREDICTIONS_PATH = "predictions/predictions_3.json"

# All columns to load from the mart (superset — we select features after encoding)
LOAD_COLS = [
    "transaction_id",
    "transaction_date",
    "merchant_id",
    # amount
    "amount",
    "abs_amount",
    "log_amount",
    "is_expense",
    "amount_to_limit_ratio",
    "amount_zscore",
    "client_avg_amount_last50",
    "client_std_amount_last50",
    "amount_vs_client_max",
    "above_client_p90",
    # time
    "txn_hour",
    "txn_day_of_week",
    "txn_month",
    "txn_year",
    "is_weekend",
    # errors
    "has_bad_cvv",
    "has_bad_expiration",
    "has_bad_card_number",
    "has_bad_pin",
    "has_insufficient_balance",
    "has_technical_glitch",
    "has_any_error",
    "card_errors_7d",
    # channel + geographic
    "is_online",
    "is_out_of_home_state",
    # velocity
    "seconds_since_last_txn",
    "card_txn_count_1h",
    "card_txn_count_24h",
    "card_txn_count_7d",
    "card_amount_sum_24h",
    # inter-purchase gap stats (Exp 8)
    "gap_zscore",
    # behavioral
    "card_mcc_freq",
    "card_merchant_freq",
    "card_distinct_mcc_7d",
    "client_distinct_cards_24h",
    "is_new_merchant",
    "is_new_mcc",
    "rapid_succession",
    # combined risk signals (Exp 8)
    "online_new_merchant",
    "online_high_amount",
    "oos_new_merchant",
    "error_online",
    # card (Exp 8)
    "credit_limit",
    "card_has_chip",
    "card_age_months",
    # user
    "current_age",
    "credit_score",
    "total_debt",
    "yearly_income",
    "debt_to_income_ratio",
    # categorical
    "use_chip",
    "card_brand",
    "card_type",
    "mcc",
]

# Features used by the model (after target encoding adds new columns)
FEATURE_COLS = [
    # amount + spending anomaly (Exp 8)
    "amount",
    "abs_amount",
    "log_amount",
    "is_expense",
    "amount_to_limit_ratio",
    "amount_zscore",
    "client_avg_amount_last50",
    "client_std_amount_last50",
    "amount_vs_client_max",
    "above_client_p90",
    # time
    "txn_hour",
    "txn_day_of_week",
    "txn_month",
    "txn_year",
    "is_weekend",
    # errors
    "has_bad_cvv",
    "has_bad_expiration",
    "has_bad_card_number",
    "has_bad_pin",
    "has_insufficient_balance",
    "has_technical_glitch",
    "has_any_error",
    "card_errors_7d",
    # channel + geographic
    "is_online",
    "is_out_of_home_state",
    # velocity
    "seconds_since_last_txn",
    "card_txn_count_1h",
    "card_txn_count_24h",
    "card_txn_count_7d",
    "card_amount_sum_24h",
    # inter-purchase gap (Exp 8)
    "gap_zscore",
    # behavioral
    "card_mcc_freq",
    "card_merchant_freq",
    "card_distinct_mcc_7d",
    "client_distinct_cards_24h",
    "is_new_merchant",
    "is_new_mcc",
    "rapid_succession",
    # combined risk signals (Exp 8)
    "online_new_merchant",
    "online_high_amount",
    "oos_new_merchant",
    "error_online",
    # card (Exp 8)
    "credit_limit",
    "card_has_chip",
    "card_age_months",
    # user
    "current_age",
    "credit_score",
    "total_debt",
    "yearly_income",
    "debt_to_income_ratio",
    # categorical
    "use_chip",
    "card_brand",
    "card_type",
    # target-encoded (Exp 5)
    "mcc_te",
    "merchant_id_te",
]

CATEGORICAL_COLS = ["use_chip", "card_brand", "card_type"]

# Target encoding settings
TE_COLS = ["mcc", "merchant_id"]
TE_ALPHA = 10  # smoothing strength


# ---------- Data Loading ----------


def load_labels():
    """Load fraud labels as {transaction_id: 0/1} dict."""
    with open(LABELS_PATH) as f:
        data = json.load(f)["target"]
    return {int(k): 1 if v == "Yes" else 0 for k, v in data.items()}


def load_prediction_ids():
    """Load transaction IDs to predict from predictions_3.json."""
    with open(PREDICTIONS_PATH) as f:
        data = json.load(f)["target"]
    return [int(k) for k in data.keys()]


def load_features(con, transaction_ids, chunk_label="data"):
    """Load features from mart_fraud_features for given transaction IDs."""
    cols = ", ".join([f"f.{c}" for c in LOAD_COLS])
    ids_pd = pd.DataFrame({"transaction_id": transaction_ids})
    con.register("ids_table", ids_pd)
    df = con.sql(f"""
        SELECT {cols}
        FROM mart_fraud_features f
        INNER JOIN ids_table i ON f.transaction_id = i.transaction_id
    """).df()
    con.unregister("ids_table")
    print(f"Loaded {len(df):,} rows for {chunk_label}")
    return df


# ---------- Target Encoding ----------


def target_encode_oof(df, col, target_col, alpha=TE_ALPHA, n_splits=5):
    """Out-of-fold target encoding to prevent leakage.

    For each fold, compute smoothed fraud rate from the OTHER folds:
        encoded = (n_fraud + alpha * global_mean) / (n_total + alpha)
    """
    global_mean = df[target_col].mean()
    encoded = pd.Series(np.nan, index=df.index, name=f"{col}_te")

    kf = KFold(n_splits=n_splits, shuffle=False)  # no shuffle: respects time order
    for train_idx, val_idx in kf.split(df):
        fold_train = df.iloc[train_idx]
        stats = fold_train.groupby(col)[target_col].agg(["sum", "count"])
        stats["encoded"] = (stats["sum"] + alpha * global_mean) / (stats["count"] + alpha)
        mapping = stats["encoded"].to_dict()
        encoded.iloc[val_idx] = df.iloc[val_idx][col].map(mapping)

    # Fill unseen categories with global mean
    encoded = encoded.fillna(global_mean)
    return encoded


def target_encode_apply(df, col, train_df, target_col, alpha=TE_ALPHA):
    """Apply target encoding to new data using training statistics."""
    global_mean = train_df[target_col].mean()
    stats = train_df.groupby(col)[target_col].agg(["sum", "count"])
    stats["encoded"] = (stats["sum"] + alpha * global_mean) / (stats["count"] + alpha)
    mapping = stats["encoded"].to_dict()
    return df[col].map(mapping).fillna(global_mean)


# ---------- Feature Preparation ----------


def prepare_features(df):
    """Convert types and handle nulls."""
    df = df.copy()
    for col in CATEGORICAL_COLS:
        df[col] = df[col].astype("category")
    if "card_has_chip" in df.columns:
        df["card_has_chip"] = df["card_has_chip"].astype(int)
    # Fill NaN in velocity/behavioral features
    fill_zero = [
        "seconds_since_last_txn",
        "card_txn_count_1h",
        "card_txn_count_24h",
        "card_txn_count_7d",
        "card_amount_sum_24h",
        "card_mcc_freq",
        "card_merchant_freq",
        "amount_zscore",
        "card_errors_7d",
        "client_distinct_cards_24h",
        "client_avg_amount_last50",
        "client_std_amount_last50",
        "amount_vs_client_max",
        "above_client_p90",
        "gap_zscore",
        "card_age_months",
    ]
    for col in fill_zero:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    return df


# ---------- Evaluation ----------


def evaluate(y_true, proba, label=""):
    """Evaluate model: AUPRC, best BA threshold, best F1 threshold."""
    auprc = average_precision_score(y_true, proba)
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"AUPRC (Average Precision): {auprc:.4f}")

    best_ba, best_ba_t = 0, 0.5
    best_f1, best_f1_t = 0, 0.5
    for t in np.arange(0.01, 0.99, 0.01):
        p = (proba >= t).astype(int)
        ba = balanced_accuracy_score(y_true, p)
        f1 = f1_score(y_true, p, zero_division=0)
        if ba > best_ba:
            best_ba, best_ba_t = ba, t
        if f1 > best_f1:
            best_f1, best_f1_t = f1, t

    # BA-optimal
    preds_ba = (proba >= best_ba_t).astype(int)
    print("\n--- Hackathon (BA optimized) ---")
    print(f"Threshold: {best_ba_t:.2f}, BA: {best_ba:.4f}")
    print(classification_report(y_true, preds_ba, target_names=["No Fraud", "Fraud"]))

    # F1-optimal
    preds_f1 = (proba >= best_f1_t).astype(int)
    f1_val = f1_score(y_true, preds_f1)
    prec_val = precision_score(y_true, preds_f1, zero_division=0)
    rec_val = recall_score(y_true, preds_f1, zero_division=0)
    print("--- Production (F1 optimized) ---")
    print(f"Threshold: {best_f1_t:.2f}, F1: {f1_val:.4f}, P: {prec_val:.4f}, R: {rec_val:.4f}")
    print(classification_report(y_true, preds_f1, target_names=["No Fraud", "Fraud"]))

    return auprc, best_ba, best_ba_t, f1_val, best_f1_t, prec_val, rec_val


# ---------- Focal Loss ----------

FOCAL_GAMMA = 2.0
FOCAL_ALPHA = 0.25


def focal_loss_objective(y_true, y_pred):
    """Focal loss for LightGBM custom objective.

    Focuses learning on hard-to-classify examples by down-weighting easy negatives.
    This eliminates the need for scale_pos_weight tuning.
    """
    p = 1.0 / (1.0 + np.exp(-y_pred))  # sigmoid
    pt = np.where(y_true == 1, p, 1 - p)
    focal_weight = FOCAL_ALPHA * (1 - pt) ** FOCAL_GAMMA

    grad = focal_weight * (p - y_true)
    hess = focal_weight * p * (1 - p)
    hess = np.maximum(hess, 1e-7)

    return grad, hess


def focal_loss_eval(y_true, y_pred):
    """Focal loss evaluation metric for LightGBM."""
    p = 1.0 / (1.0 + np.exp(-y_pred))
    pt = np.where(y_true == 1, p, 1 - p)
    loss = -FOCAL_ALPHA * (1 - pt) ** FOCAL_GAMMA * np.log(pt + 1e-8)
    return "focal_loss", np.mean(loss), False


# ---------- Main Pipeline ----------


def train_and_predict():
    """Train fraud detection model and write predictions to predictions_3.json."""
    labels = load_labels()
    pred_ids = load_prediction_ids()

    con = duckdb.connect(DB_PATH, read_only=False)
    train_df = load_features(con, list(labels.keys()), "training")
    train_df["label"] = train_df["transaction_id"].map(labels)
    train_df = train_df.dropna(subset=["label"])

    pred_df = load_features(con, pred_ids, "prediction")
    con.close()

    # Sort by time for temporal split
    train_df = train_df.sort_values("transaction_date").reset_index(drop=True)

    # Target encoding (out-of-fold on training, apply on prediction)
    print("\nApplying target encoding...")
    for col in TE_COLS:
        train_df[f"{col}_te"] = target_encode_oof(train_df, col, "label")
        pred_df[f"{col}_te"] = target_encode_apply(pred_df, col, train_df, "label")
        print(f"  {col}_te: train mean={train_df[f'{col}_te'].mean():.6f}, pred mean={pred_df[f'{col}_te'].mean():.6f}")

    # Prepare features
    train_df = prepare_features(train_df)
    pred_df = prepare_features(pred_df)

    # Time-based split: train (85%) | val (15%)
    split_idx = int(len(train_df) * 0.85)
    train_set = train_df.iloc[:split_idx]
    val_set = train_df.iloc[split_idx:]

    X_train = train_set[FEATURE_COLS]
    y_train = train_set["label"].astype(int)
    X_val = val_set[FEATURE_COLS]
    y_val = val_set["label"].astype(int)

    print(f"\nTrain: {len(X_train):,} ({y_train.mean():.4%} fraud)")
    print(f"Val:   {len(X_val):,} ({y_val.mean():.4%} fraud)")
    print(f"Train period: {train_set['transaction_date'].min()} → {train_set['transaction_date'].max()}")
    print(f"Val period:   {val_set['transaction_date'].min()} → {val_set['transaction_date'].max()}")
    print(f"Features: {len(FEATURE_COLS)}")

    # --- LightGBM with Focal Loss (Exp 6 best config) ---
    model = lgb.LGBMClassifier(
        objective=focal_loss_objective,
        n_estimators=1000,
        learning_rate=0.05,
        max_depth=6,
        num_leaves=63,
        min_child_samples=300,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.5,
        reg_lambda=2.0,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        eval_metric=focal_loss_eval,
        callbacks=[
            lgb.early_stopping(100, verbose=True),
            lgb.log_evaluation(100),
        ],
    )

    # Evaluate
    val_raw = model.predict(X_val, raw_score=True)
    val_proba = 1.0 / (1.0 + np.exp(-val_raw))
    auprc, ba, ba_t, f1, f1_t, prec, rec = evaluate(
        y_val, val_proba, "Final Model (Exp 8 fixed): Focal Loss + Target Encoding + Card Age + Gap Z-score"
    )

    # Feature importance
    importance = sorted(
        zip(FEATURE_COLS, model.feature_importances_),
        key=lambda x: x[1],
        reverse=True,
    )
    print("\nTop 20 features:")
    for feat, imp in importance[:20]:
        print(f"  {feat:35s} {imp}")

    # --- Predict & Write ---
    X_pred = pred_df[FEATURE_COLS]
    pred_raw = model.predict(X_pred, raw_score=True)
    pred_proba = 1.0 / (1.0 + np.exp(-pred_raw))
    predictions = (pred_proba >= ba_t).astype(int)

    with open(PREDICTIONS_PATH) as f:
        output = json.load(f)

    pred_id_map = dict(zip(pred_df["transaction_id"], predictions))
    for tid_str in output["target"]:
        output["target"][tid_str] = "Yes" if pred_id_map.get(int(tid_str), 0) == 1 else "No"

    with open(PREDICTIONS_PATH, "w") as f:
        json.dump(output, f)

    fraud_preds = sum(1 for v in output["target"].values() if v == "Yes")
    print(f"\nPredictions written to {PREDICTIONS_PATH}")
    print(
        f"Predicted fraud: {fraud_preds:,} / {len(output['target']):,} ({fraud_preds / len(output['target']) * 100:.2f}%)"
    )

    return auprc, ba, f1, importance


if __name__ == "__main__":
    auprc, ba, f1, importance = train_and_predict()

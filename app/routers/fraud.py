from fastapi import APIRouter, HTTPException, Request

from app.schemas import FraudRequest, FraudResponse

router = APIRouter()

FRAUD_THRESHOLD = 0.35


@router.post("/fraud", response_model=FraudResponse)
def predict_fraud(request: Request, body: FraudRequest):
    models = request.app.state.models

    if "fraud_model" not in models:
        raise HTTPException(status_code=503, detail="Fraud model not loaded")

    model = models["fraud_model"]
    te = models.get("target_encodings", {})
    meta = models.get("feature_metadata", {})
    feature_cols = meta.get("fraud_features", [])

    # Build feature vector from request
    features = {
        "amount": body.amount,
        "abs_amount": abs(body.amount),
        "log_amount": __import__("math").log(abs(body.amount) + 1),
        "is_expense": int(body.amount < 0),
        "is_online": body.is_online,
        "has_bad_cvv": body.has_bad_cvv,
        "has_any_error": body.has_any_error,
        "txn_hour": body.txn_hour,
        "credit_limit": body.credit_limit,
        "credit_score": body.credit_score,
        "card_txn_count_24h": body.card_txn_count_24h,
        "seconds_since_last_txn": body.seconds_since_last_txn or 0,
        "use_chip": body.use_chip,
        "mcc": body.mcc,
        "merchant_id": body.merchant_id,
    }

    # Apply target encoding if available
    if "mcc" in te:
        features["mcc_te"] = te["mcc"].get(body.mcc, te["mcc"].get("__global_mean__", 0))
    if "merchant_id" in te:
        features["merchant_id_te"] = te["merchant_id"].get(
            body.merchant_id, te["merchant_id"].get("__global_mean__", 0)
        )

    # Fill missing features with 0
    import pandas as pd

    df = pd.DataFrame([features])
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0

    if feature_cols:
        df = df[feature_cols]

    # Convert categorical columns to match training dtype
    cat_cols = ["use_chip", "card_brand", "card_type"]
    for col in cat_cols:
        if col in df.columns:
            df[col] = df[col].astype("category")

    raw_score = model.predict(df)[0]
    # Focal loss returns raw logits — apply sigmoid to get probability
    import math

    prob = 1.0 / (1.0 + math.exp(-raw_score))
    is_fraud = bool(prob >= FRAUD_THRESHOLD)

    return FraudResponse(
        transaction_id=body.transaction_id,
        is_fraud=is_fraud,
        probability=float(prob),
        threshold=FRAUD_THRESHOLD,
    )

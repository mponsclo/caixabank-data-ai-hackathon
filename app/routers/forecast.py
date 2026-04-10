from fastapi import APIRouter, HTTPException, Request

from app.schemas import ForecastRequest, ForecastResponse, MonthPrediction

router = APIRouter()


@router.post("/forecast", response_model=ForecastResponse)
def predict_forecast(request: Request, body: ForecastRequest):
    models = request.app.state.models

    if not any(f"forecast_h{h}" in models for h in [1, 2, 3]):
        raise HTTPException(status_code=503, detail="Forecast models not loaded")

    meta = models.get("feature_metadata", {})
    forecast_features = meta.get("forecast_features", [])
    client_features = meta.get("client_features", {})

    # Get client's feature vector from stored metadata
    client_data = client_features.get(body.client_id)
    if client_data is None:
        raise HTTPException(status_code=404, detail=f"Client {body.client_id} not found")

    import pandas as pd

    df = pd.DataFrame([client_data])

    if forecast_features:
        for col in forecast_features:
            if col not in df.columns:
                df[col] = 0
        df = df[forecast_features]

    predictions = []
    for h in [1, 2, 3]:
        model_key = f"forecast_h{h}"
        if model_key in models:
            pred = models[model_key].predict(df)[0]
            predictions.append(
                MonthPrediction(
                    horizon=h,
                    predicted_expense=max(0.0, float(pred)),
                )
            )

    return ForecastResponse(client_id=body.client_id, predictions=predictions)

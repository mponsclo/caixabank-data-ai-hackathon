from pydantic import BaseModel, Field

# --- Health ---


class HealthResponse(BaseModel):
    status: str
    models_loaded: int


# --- Fraud Detection ---


class FraudRequest(BaseModel):
    transaction_id: str
    amount: float
    use_chip: str
    mcc: int
    merchant_id: int
    is_online: int = Field(ge=0, le=1)
    has_bad_cvv: int = Field(ge=0, le=1, default=0)
    has_any_error: int = Field(ge=0, le=1, default=0)
    txn_hour: int = Field(ge=0, le=23)
    credit_limit: float = 0.0
    credit_score: int = 0
    card_txn_count_24h: int = 0
    seconds_since_last_txn: float | None = None


class FraudResponse(BaseModel):
    transaction_id: str
    is_fraud: bool
    probability: float
    threshold: float


# --- Expense Forecasting ---


class ForecastRequest(BaseModel):
    client_id: int


class MonthPrediction(BaseModel):
    horizon: int
    predicted_expense: float


class ForecastResponse(BaseModel):
    client_id: int
    predictions: list[MonthPrediction]


# --- Agent Report ---


class AgentRequest(BaseModel):
    client_id: int
    prompt: str


class AgentResponse(BaseModel):
    client_id: int
    start_date: str | None
    end_date: str | None
    backend_used: str
    message: str

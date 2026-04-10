from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.model_loader import load_models
from app.routers import agent, forecast, fraud, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ML models at startup, release on shutdown."""
    models = load_models()
    app.state.models = models
    yield


app = FastAPI(
    title="CaixaBank AI API",
    description="Fraud detection, expense forecasting, and financial report generation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(fraud.router, prefix="/predict", tags=["predictions"])
app.include_router(forecast.router, prefix="/predict", tags=["predictions"])
app.include_router(agent.router, prefix="/report", tags=["agent"])

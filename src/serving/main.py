"""FastAPI serving application for StockFlow predictions."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import mlflow
import mlflow.pyfunc
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ─────────────────────────────────────────
# Model loading
# ─────────────────────────────────────────
_model: mlflow.pyfunc.PyFuncModel | None = None


def _load_model() -> mlflow.pyfunc.PyFuncModel:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    model_name = os.getenv("MLFLOW_MODEL_NAME", "stockflow")
    model_stage = os.getenv("MLFLOW_MODEL_STAGE", "Production")

    mlflow.set_tracking_uri(tracking_uri)
    model_uri = f"models:/{model_name}/{model_stage}"
    return mlflow.pyfunc.load_model(model_uri)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    try:
        _model = _load_model()
    except Exception as exc:
        print(f"[WARNING] Could not load model at startup: {exc}")
    yield


# ─────────────────────────────────────────
# App
# ─────────────────────────────────────────
app = FastAPI(
    title="StockFlow Prediction API",
    description="Predicts next-day stock price direction.",
    version="0.1.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────
class PredictRequest(BaseModel):
    ticker: str = Field(..., example="005930.KS")
    features: dict[str, float] = Field(
        ...,
        description="Feature dict matching the trained model's input schema.",
        example={"ema_10": 75000.0, "rsi_14": 52.3},
    )


class PredictResponse(BaseModel):
    ticker: str
    prediction: int = Field(..., description="1 = up, 0 = down")
    probability_up: float


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────
@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "model_loaded": _model is not None}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded.")

    input_df = pd.DataFrame([req.features])
    try:
        proba = _model.predict(input_df)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    prob_up = float(proba[0]) if proba.ndim == 1 else float(proba[0][1])
    return PredictResponse(
        ticker=req.ticker,
        prediction=int(prob_up >= 0.5),
        probability_up=round(prob_up, 4),
    )

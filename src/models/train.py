"""LightGBM training with MLflow tracking and model registration.

Reads engineered feature sets from MinIO (processed/), trains a binary
classifier for next-day price direction, logs params/metrics to MLflow,
and registers the model so the serving API can load it from the registry.

Environment variables:
    MLFLOW_TRACKING_URI      MLflow server (default: http://localhost:5000)
    MLFLOW_EXPERIMENT_NAME   Experiment name (default: stockflow)
    MLFLOW_MODEL_NAME        Registered model name (default: stockflow)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import lightgbm as lgb
import mlflow
import mlflow.lightgbm
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

from src.data.storage import processed_key, read_parquet

logger = logging.getLogger(__name__)

TARGET_COL = "target"
DEFAULT_PARAMS: dict[str, object] = {
    "objective": "binary",
    "metric": "auc",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
}


@dataclass
class TrainResult:
    """Outcome of a training run."""

    run_id: str
    model_version: str | None
    metrics: dict[str, float] = field(default_factory=dict)


# ─────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────
def load_training_frame(tickers: list[str], on: str) -> pd.DataFrame:
    """Read processed/{ticker}/{on}.parquet for each ticker and concatenate.

    Skips tickers whose processed object is missing so a partial upstream
    run still yields a trainable frame.
    """
    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        try:
            df = read_parquet(processed_key(ticker, on))
        except Exception as exc:
            logger.warning("Skipping %s: processed data unavailable (%s)", ticker, exc)
            continue
        frames.append(df)
    if not frames:
        raise ValueError(f"No processed data found for {tickers} on {on}")
    return pd.concat(frames, axis=0).sort_index()


def split_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Split a processed frame into (X, y)."""
    if TARGET_COL not in df.columns:
        raise ValueError(f"Frame is missing '{TARGET_COL}' column")
    X = df.drop(columns=[TARGET_COL])
    y = df[TARGET_COL].astype(int)
    return X, y


def time_split(
    X: pd.DataFrame, y: pd.Series, val_fraction: float = 0.2
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Chronological train/validation split (no shuffle — avoids look-ahead leak)."""
    n_val = max(1, int(len(X) * val_fraction))
    split = len(X) - n_val
    return X.iloc[:split], X.iloc[split:], y.iloc[:split], y.iloc[split:]


# ─────────────────────────────────────────
# Training
# ─────────────────────────────────────────
def train(
    df: pd.DataFrame,
    params: dict[str, object] | None = None,
    register: bool = True,
) -> TrainResult:
    """Train a LightGBM classifier on a processed frame and log to MLflow.

    Args:
        df: Processed frame with feature columns plus a 'target' column.
        params: LightGBM params (defaults to DEFAULT_PARAMS).
        register: If True, register the logged model in the MLflow registry.

    Returns:
        TrainResult with the run id, registered version (if any), and metrics.
    """
    params = {**DEFAULT_PARAMS, **(params or {})}
    X, y = split_xy(df)
    X_train, X_val, y_train, y_val = time_split(X, y)

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT_NAME", "stockflow"))
    model_name = os.getenv("MLFLOW_MODEL_NAME", "stockflow")

    with mlflow.start_run() as run:
        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            eval_metric="auc",
            callbacks=[lgb.early_stopping(30, verbose=False)],
        )

        proba = model.predict_proba(X_val)[:, 1]
        pred = (proba >= 0.5).astype(int)
        metrics = {
            "val_accuracy": float(accuracy_score(y_val, pred)),
            "val_f1": float(f1_score(y_val, pred, zero_division=0)),
            # roc_auc is undefined when the validation slice is single-class
            "val_auc": float(roc_auc_score(y_val, proba)) if y_val.nunique() > 1 else float("nan"),
        }

        mlflow.log_params(params)
        mlflow.log_metric("n_train", len(X_train))
        mlflow.log_metric("n_val", len(X_val))
        for name, value in metrics.items():
            mlflow.log_metric(name, value)

        model_version = None
        registered = model_name if register else None
        mlflow.lightgbm.log_model(
            model.booster_,
            artifact_path="model",
            registered_model_name=registered,
        )
        if register:
            client = mlflow.MlflowClient()
            versions = client.get_latest_versions(model_name, stages=["None"])
            if versions:
                model_version = versions[0].version

        logger.info("Run %s metrics: %s", run.info.run_id, metrics)
        return TrainResult(
            run_id=run.info.run_id, model_version=model_version, metrics=metrics
        )


def train_from_storage(
    tickers: list[str], on: str, params: dict[str, object] | None = None
) -> TrainResult:
    """Convenience: load processed data from MinIO, then train + register."""
    df = load_training_frame(tickers, on)
    return train(df, params=params)

"""StockFlow daily pipeline DAG."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "stockflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


TICKERS = ["005930.KS", "000660.KS", "AAPL", "NVDA"]


def fetch_data(**context):
    """Pull latest OHLCV data and save raw Parquet to MinIO."""
    import sys
    sys.path.insert(0, "/opt/airflow")
    from src.data.fetcher import fetch_multiple
    from src.data.storage import ensure_bucket, raw_key, write_parquet

    execution_date = context["ds"]
    ensure_bucket()
    data = fetch_multiple(TICKERS, start="2020-01-01", end=execution_date)

    saved = []
    for ticker, df in data.items():
        uri = write_parquet(df, raw_key(ticker, execution_date))
        saved.append(uri)
    print(f"Fetched {len(data)} tickers, saved {len(saved)} objects to MinIO")
    if not saved:
        raise ValueError(f"No data fetched for any of {TICKERS} — failing fast")


def build_features(**context):
    """Read raw OHLCV, compute features + label, save to MinIO processed/."""
    import sys
    sys.path.insert(0, "/opt/airflow")
    from src.data.storage import processed_key, raw_key, read_parquet, write_parquet
    from src.features.engineer import build_features as build_feature_set

    execution_date = context["ds"]
    saved = []
    for ticker in TICKERS:
        try:
            raw = read_parquet(raw_key(ticker, execution_date))
        except Exception as exc:
            print(f"Skipping {ticker}: raw data unavailable ({exc})")
            continue
        X, y = build_feature_set(raw)
        processed = X.copy()
        processed["target"] = y
        uri = write_parquet(processed, processed_key(ticker, execution_date))
        saved.append(uri)
    print(f"Built features for {len(saved)} tickers, saved to MinIO")


def train_model(**context):
    """Train LightGBM on processed data, log + register to MLflow."""
    import sys
    sys.path.insert(0, "/opt/airflow")
    from src.models.train import train_from_storage

    execution_date = context["ds"]
    result = train_from_storage(TICKERS, execution_date)
    print(f"Trained run={result.run_id} version={result.model_version} metrics={result.metrics}")
    context["ti"].xcom_push(key="run_id", value=result.run_id)
    context["ti"].xcom_push(key="model_version", value=result.model_version)


def evaluate_model(**context):
    """Compare the new model against Production and promote if better."""
    import sys
    sys.path.insert(0, "/opt/airflow")
    from src.models.evaluate import evaluate_and_promote

    version = context["ti"].xcom_pull(task_ids="train_model", key="model_version")
    if not version:
        print("No model_version from train_model — skipping promotion")
        return

    result = evaluate_and_promote(version)
    print(f"Promotion: promoted={result.promoted} version={result.version} reason={result.reason}")


with DAG(
    dag_id="stockflow_pipeline",
    description="Daily stock prediction pipeline",
    schedule="0 18 * * 1-5",  # 18:00 KST on weekdays
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["stockflow", "ml"],
) as dag:
    t1 = PythonOperator(task_id="fetch_data", python_callable=fetch_data)
    t2 = PythonOperator(task_id="build_features", python_callable=build_features)
    t3 = PythonOperator(task_id="train_model", python_callable=train_model)
    t4 = PythonOperator(task_id="evaluate_model", python_callable=evaluate_model)

    t1 >> t2 >> t3 >> t4

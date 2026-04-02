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


def fetch_data(**context):
    """Pull latest OHLCV data and save to MinIO."""
    import sys
    sys.path.insert(0, "/opt/airflow")
    from src.data.fetcher import fetch_multiple

    tickers = ["005930.KS", "000660.KS", "AAPL", "NVDA"]
    execution_date = context["ds"]
    data = fetch_multiple(tickers, start="2020-01-01", end=execution_date)
    print(f"Fetched {len(data)} tickers")


def build_features(**context):
    """Compute technical indicators and save feature sets."""
    print("Feature engineering step — implement me")


def train_model(**context):
    """Train LightGBM model and log to MLflow."""
    print("Training step — implement me")


def evaluate_model(**context):
    """Compare new model against production model in MLflow."""
    print("Evaluation step — implement me")


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

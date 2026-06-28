"""S3-compatible object storage I/O (MinIO local / AWS S3 prod).

Reads connection settings from environment variables so the same code runs
against MinIO locally and AWS S3 in production:

    MLFLOW_S3_ENDPOINT_URL   S3 endpoint (e.g. http://minio:9000); unset = real AWS
    AWS_ACCESS_KEY_ID        Access key
    AWS_SECRET_ACCESS_KEY    Secret key
    AWS_DEFAULT_REGION       Region (default: ap-northeast-2)
    AWS_S3_BUCKET            Default bucket (default: stockflow-data)

Object layout (see CLAUDE.md data flow):
    raw/{ticker}/{date}.parquet         raw OHLCV from yfinance
    processed/{ticker}/{date}.parquet   engineered feature sets
"""

from __future__ import annotations

import io
import logging
import os
from datetime import date

import boto3
import pandas as pd
from botocore.client import BaseClient
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = os.getenv("AWS_S3_BUCKET", "stockflow-data")


# ─────────────────────────────────────────
# Client / config
# ─────────────────────────────────────────
def get_s3_client() -> BaseClient:
    """Create a boto3 S3 client pointed at MinIO (or AWS if endpoint unset)."""
    endpoint = os.getenv("MLFLOW_S3_ENDPOINT_URL") or None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-2"),
    )


def _storage_options() -> dict[str, object]:
    """storage_options for pandas/s3fs to reach the same endpoint."""
    endpoint = os.getenv("MLFLOW_S3_ENDPOINT_URL") or None
    opts: dict[str, object] = {
        "key": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret": os.getenv("AWS_SECRET_ACCESS_KEY"),
    }
    if endpoint:
        opts["client_kwargs"] = {"endpoint_url": endpoint}
    return opts


def ensure_bucket(bucket: str = DEFAULT_BUCKET, client: BaseClient | None = None) -> None:
    """Create the bucket if it does not already exist (idempotent)."""
    client = client or get_s3_client()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchBucket", "NotFound"):
            logger.info("Creating bucket '%s'", bucket)
            client.create_bucket(Bucket=bucket)
        else:
            raise


# ─────────────────────────────────────────
# Key builders
# ─────────────────────────────────────────
def raw_key(ticker: str, on: str | date) -> str:
    """Object key for raw OHLCV, e.g. raw/AAPL/2026-06-28.parquet."""
    return f"raw/{ticker}/{on}.parquet"


def processed_key(ticker: str, on: str | date) -> str:
    """Object key for engineered features, e.g. processed/AAPL/2026-06-28.parquet."""
    return f"processed/{ticker}/{on}.parquet"


# ─────────────────────────────────────────
# DataFrame I/O (Parquet)
# ─────────────────────────────────────────
def write_parquet(df: pd.DataFrame, key: str, bucket: str = DEFAULT_BUCKET) -> str:
    """Write a DataFrame to s3://{bucket}/{key} as Parquet. Returns the s3 URI."""
    uri = f"s3://{bucket}/{key}"
    df.to_parquet(uri, engine="pyarrow", storage_options=_storage_options())
    logger.info("Wrote %d rows -> %s", len(df), uri)
    return uri


def read_parquet(key: str, bucket: str = DEFAULT_BUCKET) -> pd.DataFrame:
    """Read a Parquet object from s3://{bucket}/{key} into a DataFrame."""
    uri = f"s3://{bucket}/{key}"
    df = pd.read_parquet(uri, engine="pyarrow", storage_options=_storage_options())
    logger.info("Read %d rows <- %s", len(df), uri)
    return df


# ─────────────────────────────────────────
# Raw bytes I/O + listing (boto3)
# ─────────────────────────────────────────
def write_bytes(
    data: bytes, key: str, bucket: str = DEFAULT_BUCKET, client: BaseClient | None = None
) -> str:
    """Upload raw bytes to s3://{bucket}/{key}. Returns the s3 URI."""
    client = client or get_s3_client()
    client.put_object(Bucket=bucket, Key=key, Body=io.BytesIO(data))
    return f"s3://{bucket}/{key}"


def read_bytes(
    key: str, bucket: str = DEFAULT_BUCKET, client: BaseClient | None = None
) -> bytes:
    """Download s3://{bucket}/{key} as raw bytes."""
    client = client or get_s3_client()
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def object_exists(
    key: str, bucket: str = DEFAULT_BUCKET, client: BaseClient | None = None
) -> bool:
    """Return True if s3://{bucket}/{key} exists."""
    client = client or get_s3_client()
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def list_keys(
    prefix: str = "", bucket: str = DEFAULT_BUCKET, client: BaseClient | None = None
) -> list[str]:
    """List object keys under a prefix (handles pagination)."""
    client = client or get_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    return keys

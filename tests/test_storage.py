"""Tests for src.data.storage — boto3 client is mocked via injection."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.data import storage


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code}}, "Op")


# ── key builders ─────────────────────────────────────────
def test_key_builders():
    assert storage.raw_key("AAPL", "2026-06-28") == "raw/AAPL/2026-06-28.parquet"
    assert storage.processed_key("AAPL", "2026-06-28") == "processed/AAPL/2026-06-28.parquet"


# ── object_exists ────────────────────────────────────────
def test_object_exists_true():
    client = MagicMock()
    assert storage.object_exists("raw/x.parquet", client=client) is True
    client.head_object.assert_called_once()


def test_object_exists_false_on_404():
    client = MagicMock()
    client.head_object.side_effect = _client_error("404")
    assert storage.object_exists("raw/missing.parquet", client=client) is False


def test_object_exists_reraises_other_errors():
    client = MagicMock()
    client.head_object.side_effect = _client_error("AccessDenied")
    with pytest.raises(ClientError):
        storage.object_exists("raw/x.parquet", client=client)


# ── ensure_bucket ────────────────────────────────────────
def test_ensure_bucket_creates_when_missing():
    client = MagicMock()
    client.head_bucket.side_effect = _client_error("404")
    storage.ensure_bucket("b", client=client)
    client.create_bucket.assert_called_once_with(Bucket="b")


def test_ensure_bucket_noop_when_present():
    client = MagicMock()
    storage.ensure_bucket("b", client=client)
    client.create_bucket.assert_not_called()


# ── list_keys (pagination) ───────────────────────────────
def test_list_keys_handles_pagination():
    client = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Contents": [{"Key": "raw/a"}, {"Key": "raw/b"}]},
        {"Contents": [{"Key": "raw/c"}]},
        {},  # empty page (no Contents)
    ]
    client.get_paginator.return_value = paginator
    assert storage.list_keys("raw/", client=client) == ["raw/a", "raw/b", "raw/c"]


# ── bytes round-trip ─────────────────────────────────────
def test_read_bytes():
    client = MagicMock()
    client.get_object.return_value = {"Body": MagicMock(read=lambda: b"data")}
    assert storage.read_bytes("k", client=client) == b"data"

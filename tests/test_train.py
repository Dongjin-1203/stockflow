"""Tests for src.models.train — pure helpers + storage loading (mocked)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.models import train


def _processed(n=50, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"f1": rng.normal(size=n), "f2": rng.normal(size=n)}, index=idx
    )
    df["target"] = rng.integers(0, 2, n)
    return df


def test_split_xy_separates_target():
    df = _processed()
    X, y = train.split_xy(df)
    assert "target" not in X.columns
    assert list(X.columns) == ["f1", "f2"]
    assert len(y) == len(df)


def test_split_xy_missing_target_raises():
    with pytest.raises(ValueError, match="target"):
        train.split_xy(pd.DataFrame({"f1": [1, 2]}))


def test_time_split_is_chronological():
    df = _processed(n=100)
    X, y = train.split_xy(df)
    X_tr, X_val, y_tr, y_val = train.time_split(X, y, val_fraction=0.2)
    assert len(X_val) == 20
    assert len(X_tr) == 80
    # validation strictly follows training in time (no shuffle / leak)
    assert X_tr.index.max() < X_val.index.min()


def test_load_training_frame_concatenates(monkeypatch):
    store = {
        "processed/AAPL/2024-01-01.parquet": _processed(10, seed=1),
        "processed/NVDA/2024-01-01.parquet": _processed(10, seed=2),
    }
    monkeypatch.setattr(
        train, "read_parquet", lambda key, *a, **k: store[key]
    )
    df = train.load_training_frame(["AAPL", "NVDA"], "2024-01-01")
    assert len(df) == 20


def test_load_training_frame_skips_missing(monkeypatch):
    def fake_read(key, *a, **k):
        if "NVDA" in key:
            raise FileNotFoundError(key)
        return _processed(10)

    monkeypatch.setattr(train, "read_parquet", fake_read)
    df = train.load_training_frame(["AAPL", "NVDA"], "2024-01-01")
    assert len(df) == 10  # only AAPL loaded


def test_load_training_frame_all_missing_raises(monkeypatch):
    monkeypatch.setattr(
        train, "read_parquet", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())
    )
    with pytest.raises(ValueError, match="No processed data"):
        train.load_training_frame(["AAPL"], "2024-01-01")

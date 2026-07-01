"""Tests for src.data.fetcher — yfinance is monkeypatched, no network."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data import fetcher


def _flat_frame(cols=("Open", "High", "Low", "Close", "Volume")):
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    return pd.DataFrame({c: [1.0, 2.0, 3.0] for c in cols}, index=idx)


def _multiindex_frame(ticker="AAPL"):
    """Mimic yfinance >=0.2.50 single-ticker output (MultiIndex columns)."""
    df = _flat_frame()
    df.columns = pd.MultiIndex.from_product([df.columns, [ticker]])
    return df


def test_fetch_ohlcv_returns_ohlcv_columns(monkeypatch):
    monkeypatch.setattr(fetcher.yf, "download", lambda *a, **k: _flat_frame())
    out = fetcher.fetch_ohlcv("AAPL", "2024-01-01", "2024-01-04")
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert out.index.name == "date"


def test_fetch_ohlcv_flattens_multiindex_columns(monkeypatch):
    monkeypatch.setattr(fetcher.yf, "download", lambda *a, **k: _multiindex_frame())
    out = fetcher.fetch_ohlcv("AAPL", "2024-01-01", "2024-01-04")
    # ticker level dropped -> Close is a Series, not a frame
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert out["Close"].tolist() == [1.0, 2.0, 3.0]


def test_fetch_ohlcv_empty_raises(monkeypatch):
    monkeypatch.setattr(fetcher.yf, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError, match="No data returned"):
        fetcher.fetch_ohlcv("BADTICKER", "2024-01-01", "2024-01-04")


def test_fetch_multiple_skips_failures(monkeypatch):
    def fake_download(ticker, *a, **k):
        if ticker == "BAD":
            return pd.DataFrame()  # triggers ValueError inside fetch_ohlcv
        return _flat_frame()

    monkeypatch.setattr(fetcher.yf, "download", fake_download)
    result = fetcher.fetch_multiple(["AAPL", "BAD", "NVDA"], "2024-01-01", "2024-01-04")
    assert set(result) == {"AAPL", "NVDA"}  # BAD skipped, others kept

"""Tests for src.features.engineer — pure pandas/ta, no network."""

from __future__ import annotations

from src.features.engineer import add_technical_indicators, build_features, build_label

OHLCV_COLS = {"Open", "High", "Low", "Close", "Volume"}
EXPECTED_FEATURES = {
    "ema_10", "ema_30", "macd", "macd_signal", "rsi_14", "stoch_k",
    "bb_high", "bb_low", "bb_width", "atr", "obv",
}


def test_add_technical_indicators_adds_all_features(ohlcv):
    out = add_technical_indicators(ohlcv)
    assert EXPECTED_FEATURES.issubset(out.columns)
    # original frame is not mutated
    assert not EXPECTED_FEATURES.issubset(ohlcv.columns)


def test_build_label_is_binary_and_shifted(ohlcv):
    out = build_label(ohlcv, horizon=1)
    assert set(out["target"].unique()).issubset({0, 1})
    # last row of the original has no "next day" -> dropped by dropna
    assert len(out) < len(ohlcv)


def test_build_features_returns_aligned_xy_without_nans(ohlcv):
    X, y = build_features(ohlcv, horizon=1)
    assert len(X) == len(y)
    assert not X.isna().any().any()
    # feature engineering drops the raw OHLCV and the target from X
    assert OHLCV_COLS.isdisjoint(X.columns)
    assert "target" not in X.columns
    assert EXPECTED_FEATURES.issubset(X.columns)


def test_build_features_horizon_changes_label(ohlcv):
    _, y1 = build_features(ohlcv, horizon=1)
    _, y5 = build_features(ohlcv, horizon=5)
    # a longer horizon drops more trailing rows
    assert len(y5) < len(y1)

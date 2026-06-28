"""Feature engineering for stock price prediction."""

from __future__ import annotations

import pandas as pd
import ta


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Append technical analysis features to an OHLCV DataFrame.

    Input columns expected: Open, High, Low, Close, Volume.
    Returns a new DataFrame with additional feature columns.
    """
    df = df.copy()

    # Trend
    df["ema_10"] = ta.trend.EMAIndicator(df["Close"], window=10).ema_indicator()
    df["ema_30"] = ta.trend.EMAIndicator(df["Close"], window=30).ema_indicator()
    df["macd"] = ta.trend.MACD(df["Close"]).macd()
    df["macd_signal"] = ta.trend.MACD(df["Close"]).macd_signal()

    # Momentum
    df["rsi_14"] = ta.momentum.RSIIndicator(df["Close"], window=14).rsi()
    df["stoch_k"] = ta.momentum.StochasticOscillator(
        df["High"], df["Low"], df["Close"]
    ).stoch()

    # Volatility
    bb = ta.volatility.BollingerBands(df["Close"])
    df["bb_high"] = bb.bollinger_hband()
    df["bb_low"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()
    df["atr"] = ta.volatility.AverageTrueRange(
        df["High"], df["Low"], df["Close"]
    ).average_true_range()

    # Volume
    df["obv"] = ta.volume.OnBalanceVolumeIndicator(df["Close"], df["Volume"]).on_balance_volume()

    return df


def build_label(df: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """Add binary target: 1 if the close `horizon` days ahead exceeds today's.

    The trailing `horizon` rows have no known future close, so they are
    invalidated (NaN) and dropped rather than mislabeled as 0 — otherwise a
    bogus "down" label would leak into the training set.
    """
    df = df.copy()
    future_close = df["Close"].shift(-horizon)
    df["target"] = (future_close > df["Close"]).astype(float)
    df.loc[future_close.isna(), "target"] = float("nan")
    df = df.dropna()
    df["target"] = df["target"].astype(int)
    return df


def build_features(df: pd.DataFrame, horizon: int = 1) -> tuple[pd.DataFrame, pd.Series]:
    """Full feature engineering pipeline.

    Returns:
        (X, y) tuple ready for model training.
    """
    df = add_technical_indicators(df)
    df = build_label(df, horizon=horizon)
    drop_cols = ["Open", "High", "Low", "Close", "Volume", "target"]
    X = df.drop(columns=drop_cols)
    y = df["target"]
    return X, y

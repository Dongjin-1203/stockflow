"""Stock price data fetcher using yfinance."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_ohlcv(
    ticker: str,
    start: str | date,
    end: str | date,
    interval: str = "1d",
) -> pd.DataFrame:
    """Download OHLCV data for a single ticker.

    Args:
        ticker: Yahoo Finance ticker symbol (e.g. "005930.KS", "AAPL").
        start: Start date (inclusive), "YYYY-MM-DD" or date object.
        end: End date (exclusive), "YYYY-MM-DD" or date object.
        interval: Data interval ("1d", "1h", etc.).

    Returns:
        DataFrame with columns [Open, High, Low, Close, Volume].
    """
    logger.info("Fetching %s from %s to %s (interval=%s)", ticker, start, end, interval)
    df = yf.download(ticker, start=str(start), end=str(end), interval=interval, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'")
    df.index.name = "date"
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_multiple(
    tickers: list[str],
    start: str | date,
    end: str | date,
    interval: str = "1d",
) -> dict[str, pd.DataFrame]:
    """Download OHLCV data for multiple tickers.

    Returns:
        Dict mapping ticker -> DataFrame.
    """
    result: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            result[ticker] = fetch_ohlcv(ticker, start, end, interval)
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", ticker, exc)
    return result

"""FinanceDataReader 기반 시세 조회 클라이언트.

모든 함수는 실패 시 None을 반환해 앱이 죽지 않도록 한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import FinanceDataReader as fdr
import pandas as pd
import streamlit as st


def _date_range(period_days: int) -> tuple[str, str]:
    """오늘 기준 period_days일 전 ~ 오늘 (YYYY-MM-DD)."""
    end = datetime.now()
    start = end - timedelta(days=period_days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@st.cache_data(ttl=300)
def get_index(symbol: str, period_days: int = 90) -> pd.DataFrame | None:
    """지수 시세 조회. symbol 예: 'KS11'(코스피), 'KQ11'(코스닥).

    반환 컬럼: Date, Close, Change(전일 대비 등락률 %)
    """
    try:
        start, end = _date_range(period_days)
        df = fdr.DataReader(symbol, start, end)
        if df is None or df.empty:
            return None

        df = df.reset_index()
        # 날짜 컬럼명 표준화 (FDR은 'Date' 인덱스 사용)
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        out = pd.DataFrame(
            {
                "Date": pd.to_datetime(df[date_col]),
                "Close": df["Close"].astype(float),
            }
        )
        # 전일 대비 등락률 (%)
        out["Change"] = out["Close"].pct_change() * 100
        return out
    except Exception as e:  # noqa: BLE001 - 앱이 죽지 않도록 방어
        print(f"[fdr_client.get_index] {symbol} 조회 실패: {e}")
        return None


@st.cache_data(ttl=300)
def get_exchange_rate(symbol: str = "USD/KRW", period_days: int = 90) -> pd.DataFrame | None:
    """환율 시세 조회. 기본 'USD/KRW'.

    반환 컬럼: Date, Close, Change(전일 대비 등락률 %)
    """
    try:
        start, end = _date_range(period_days)
        df = fdr.DataReader(symbol, start, end)
        if df is None or df.empty:
            return None

        df = df.reset_index()
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        out = pd.DataFrame(
            {
                "Date": pd.to_datetime(df[date_col]),
                "Close": df["Close"].astype(float),
            }
        )
        out["Change"] = out["Close"].pct_change() * 100
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[fdr_client.get_exchange_rate] {symbol} 조회 실패: {e}")
        return None


@st.cache_data(ttl=300)
def get_stock(ticker: str, period_days: int = 90) -> pd.DataFrame | None:
    """개별 종목 시세 조회.

    반환 컬럼: Date, Close, Change(전일 대비 등락률 %)
    """
    try:
        start, end = _date_range(period_days)
        df = fdr.DataReader(ticker, start, end)
        if df is None or df.empty:
            return None

        df = df.reset_index()
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        out = pd.DataFrame(
            {
                "Date": pd.to_datetime(df[date_col]),
                "Close": df["Close"].astype(float),
            }
        )
        out["Change"] = out["Close"].pct_change() * 100
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[fdr_client.get_stock] {ticker} 조회 실패: {e}")
        return None


@st.cache_data(ttl=300)
def get_latest_price(symbol: str) -> dict | None:
    """가장 최근 종가 + 전일 대비 등락률 반환.

    반환: {"price": float, "change_pct": float, "date": str}
    환율 심볼('USD/KRW' 등)도 동일하게 처리한다.
    """
    try:
        # 최근 영업일 여유를 위해 14일 조회
        df = get_stock(symbol, period_days=14)
        if df is None or df.empty:
            return None

        last = df.iloc[-1]
        change_pct = last["Change"]
        return {
            "price": float(last["Close"]),
            "change_pct": float(change_pct) if pd.notna(change_pct) else 0.0,
            "date": pd.to_datetime(last["Date"]).strftime("%Y-%m-%d"),
        }
    except Exception as e:  # noqa: BLE001
        print(f"[fdr_client.get_latest_price] {symbol} 조회 실패: {e}")
        return None

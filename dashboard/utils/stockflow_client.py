"""StockFlow 예측 API 클라이언트.

StockFlow FastAPI 서빙의 /predict/ticker/{ticker} 엔드포인트를 호출해
퀀트 모델의 다음 거래일 등락 예측을 가져온다.
실패 시 None을 반환해 대시보드가 죽지 않도록 한다(graceful).

환경변수:
    STOCKFLOW_API_URL   StockFlow 서빙 주소 (기본: http://localhost:8000)
"""
from __future__ import annotations

import os

import requests
import streamlit as st

API_URL = os.getenv("STOCKFLOW_API_URL", "http://localhost:8000")
_TIMEOUT = 15


def _to_yf_symbol(code: str) -> str:
    """대시보드 종목코드를 StockFlow(yfinance) 심볼로 변환.

    6자리 숫자 한국 종목코드는 KOSPI 접미사 '.KS'를 붙인다(예: 005930 → 005930.KS).
    이미 접미사가 있거나 해외 티커(AAPL 등)는 그대로 둔다.
    """
    code = code.strip()
    if code.isdigit() and len(code) == 6:
        return f"{code}.KS"
    return code


@st.cache_data(ttl=600)
def get_prediction(code: str) -> dict | None:
    """종목의 다음 거래일 등락 예측 조회.

    반환: {"prediction": 0|1, "probability_up": float} 또는 None(실패).
    """
    symbol = _to_yf_symbol(code)
    try:
        resp = requests.get(f"{API_URL}/predict/ticker/{symbol}", timeout=_TIMEOUT)
        if resp.status_code != 200:
            print(f"[stockflow_client] {symbol} 예측 실패: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        return {
            "prediction": data.get("prediction"),
            "probability_up": data.get("probability_up"),
        }
    except Exception as e:  # noqa: BLE001 - 대시보드가 죽지 않도록 방어
        print(f"[stockflow_client] {symbol} 예측 조회 오류: {e}")
        return None


def get_predictions(codes: list[str]) -> dict[str, dict]:
    """여러 종목 예측을 {코드: 예측} 형태로 반환(실패 종목은 제외)."""
    out: dict[str, dict] = {}
    for code in codes:
        pred = get_prediction(code)
        if pred is not None:
            out[code] = pred
    return out

"""한국은행 ECOS OpenAPI 클라이언트 (기준금리·국고채).

API: https://ecos.bok.or.kr/api/
모든 함수는 실패 시 None을 반환해 앱이 죽지 않도록 한다.
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

ECOS_API_KEY = os.getenv("ECOS_API_KEY")

BASE_URL = (
    "https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100/"
    "{stat_code}/{cycle}/{start}/{end}/{item_code}"
)

_TIMEOUT = 10


def _shift_months(dt: datetime, months: int) -> datetime:
    """dt에서 months개월 뺀 날짜(1일 기준)."""
    total = (dt.year * 12 + (dt.month - 1)) - months
    year, month = divmod(total, 12)
    return dt.replace(year=year, month=month + 1, day=1)


def _fetch(
    stat_code: str, item_code: str, cycle: str, start: str, end: str
) -> pd.DataFrame | None:
    """ECOS StatisticSearch 호출 → DataFrame(date, value).

    실패 또는 결과 없음 시 None.
    """
    if not ECOS_API_KEY:
        print("[ecos_client] ECOS_API_KEY 미설정")
        return None
    try:
        url = BASE_URL.format(
            key=ECOS_API_KEY,
            stat_code=stat_code,
            cycle=cycle,
            start=start,
            end=end,
            item_code=item_code,
        )
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if "StatisticSearch" not in data:
            # {"RESULT": {"CODE": ..., "MESSAGE": ...}}
            result = data.get("RESULT", {})
            print(f"[ecos_client] {stat_code} 응답 오류: {result}")
            return None

        rows = data["StatisticSearch"].get("row", [])
        if not rows:
            return None

        df = pd.DataFrame(
            {
                "date": [r.get("TIME", "") for r in rows],
                "value": [
                    float(r["DATA_VALUE"])
                    for r in rows
                    if r.get("DATA_VALUE") not in (None, "")
                ],
            }
        )
        if df.empty:
            return None
        return df
    except Exception as e:  # noqa: BLE001
        print(f"[ecos_client._fetch] {stat_code} 실패: {e}")
        return None


@st.cache_data(ttl=86400)
def get_base_rate(period_months: int = 6) -> pd.DataFrame | None:
    """한국은행 기준금리 추이 (월별).

    통계표: 722Y001, 아이템: 0101000, 주기: M
    반환 컬럼: date, value
    """
    try:
        now = datetime.now()
        end = now.strftime("%Y%m")
        start = _shift_months(now, period_months).strftime("%Y%m")
        return _fetch("722Y001", "0101000", "M", start, end)
    except Exception as e:  # noqa: BLE001
        print(f"[ecos_client.get_base_rate] 실패: {e}")
        return None


@st.cache_data(ttl=86400)
def get_treasury_3y(period_months: int = 6) -> pd.DataFrame | None:
    """국고채 3년 금리 추이 (일별).

    통계표: 817Y002, 아이템: 010190000, 주기: D
    반환 컬럼: date, value
    """
    try:
        now = datetime.now()
        end = now.strftime("%Y%m%d")
        start = _shift_months(now, period_months).strftime("%Y%m%d")
        return _fetch("817Y002", "010190000", "D", start, end)
    except Exception as e:  # noqa: BLE001
        print(f"[ecos_client.get_treasury_3y] 실패: {e}")
        return None


@st.cache_data(ttl=86400)
def get_latest_base_rate() -> dict | None:
    """가장 최근 기준금리 + 직전 대비 방향.

    반환: {"rate": float, "date": str, "direction": "인상"/"인하"/"동결"}
    """
    try:
        df = get_base_rate(period_months=24)
        if df is None or df.empty:
            return None

        df = df.sort_values("date").reset_index(drop=True)
        latest = df.iloc[-1]
        rate = float(latest["value"])

        direction = "동결"
        if len(df) >= 2:
            prev = float(df.iloc[-2]["value"])
            if rate > prev:
                direction = "인상"
            elif rate < prev:
                direction = "인하"

        return {
            "rate": rate,
            "date": str(latest["date"]),
            "direction": direction,
        }
    except Exception as e:  # noqa: BLE001
        print(f"[ecos_client.get_latest_base_rate] 실패: {e}")
        return None

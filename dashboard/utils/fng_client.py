"""공포·탐욕 지수(Fear & Greed Index) 클라이언트.

Alternative.me API 사용. 실패 시 None 반환.
"""
from __future__ import annotations

import requests
import streamlit as st

FNG_URL = "https://api.alternative.me/fng/?limit=2&format=json"

_TIMEOUT = 10


def _label_kr(value: int) -> str:
    """0~100 값을 한국어 레이블로 변환."""
    if value <= 24:
        return "극단적 공포"
    if value <= 44:
        return "공포"
    if value <= 55:
        return "중립"
    if value <= 74:
        return "탐욕"
    return "극단적 탐욕"


@st.cache_data(ttl=3600)
def get_fng() -> dict | None:
    """현재/직전 공포·탐욕 지수 반환.

    반환: {"value": int, "label": str, "prev_value": int, "prev_label": str}
    """
    try:
        resp = requests.get(FNG_URL, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None

        value = int(data[0]["value"])
        prev_value = int(data[1]["value"]) if len(data) > 1 else value

        return {
            "value": value,
            "label": _label_kr(value),
            "prev_value": prev_value,
            "prev_label": _label_kr(prev_value),
        }
    except Exception as e:  # noqa: BLE001
        print(f"[fng_client.get_fng] 실패: {e}")
        return None

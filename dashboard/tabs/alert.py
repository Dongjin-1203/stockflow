"""탭 4 — 알림 조건.

조건 등록 / 점검 / 목록 표시를 제공한다. 실시간 알림이 아닌 점검 시점 기준이다.
조건은 st.session_state["alerts"]에 list[dict]로 관리한다.
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from utils.dart_client import get_corp_code, get_recent_disclosures
from utils.fdr_client import get_latest_price

TYPE_PRICE = "현재가 ≥ 목표가"
TYPE_DISCLOSURE = "공시 발생"
ALERT_TYPES = [TYPE_PRICE, TYPE_DISCLOSURE]

# 종목 코드 → 회사명 매핑 (공시 점검용)
TICKER_TO_NAME = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "000270": "기아",
    "005380": "현대차",
    "051910": "LG화학",
    "006400": "삼성SDI",
    "003550": "LG",
    "035720": "카카오",
    "096770": "SK이노베이션",
}

# 상태 문자열 → 표시 라벨
_STATUS_LABEL = {
    "충족": "✅ 충족",
    "미충족": "⏳ 미충족",
    "키없음": "🔑 키없음",
    "오류": "⚠️ 오류",
}


def _check_one(alert: dict) -> str:
    """단일 조건 점검 → 상태 문자열 반환."""
    ticker = alert["ticker"]
    try:
        if alert["type"] == TYPE_PRICE:
            data = get_latest_price(ticker)
            if data is None:
                return "오류"
            target = alert.get("target_price")
            if target is None:
                return "오류"
            return "충족" if data["price"] >= target else "미충족"

        # 공시 발생
        if not os.getenv("DART_API_KEY"):
            return "키없음"
        corp_name = TICKER_TO_NAME.get(ticker, ticker)
        corp_code = get_corp_code(corp_name)
        if corp_code is None:
            return "오류"
        disclosures = get_recent_disclosures(corp_code, limit=20)
        today = datetime.now().strftime("%Y%m%d")
        has_today = any(d.get("rcept_dt") == today for d in disclosures)
        return "충족" if has_today else "미충족"
    except Exception as e:  # noqa: BLE001
        print(f"[alert._check_one] {ticker} 점검 실패: {e}")
        return "오류"


def _run_checks() -> None:
    """모든 조건 점검 → session_state['alert_results'] 저장."""
    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    results: dict[str, dict] = {}
    with st.spinner("조건 점검 중..."):
        for idx, alert in enumerate(st.session_state["alerts"]):
            results[str(idx)] = {
                "status": _check_one(alert),
                "checked_at": checked_at,
            }
    st.session_state["alert_results"] = results


def render() -> None:
    if "alerts" not in st.session_state:
        st.session_state["alerts"] = []

    st.subheader("🔔 알림 조건")

    # ── [구역 1] 조건 등록 ──────────────────────────
    with st.form("alert_form", clear_on_submit=True):
        col_ticker, col_type, col_price = st.columns(3)
        with col_ticker:
            ticker = st.text_input("종목 코드", placeholder="예: 005930")
        with col_type:
            alert_type = st.selectbox("조건 유형", ALERT_TYPES)
        with col_price:
            target_price = st.number_input(
                "목표가", min_value=0.0, value=0.0, step=100.0
            )

        submitted = st.form_submit_button("조건 추가")
        if submitted:
            ticker = ticker.strip()
            if not ticker:
                st.warning("종목 코드를 입력해주세요.")
            else:
                st.session_state["alerts"].append(
                    {
                        "ticker": ticker,
                        "type": alert_type,
                        "target_price": (
                            float(target_price)
                            if alert_type == TYPE_PRICE
                            else None
                        ),
                        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                )
                st.success(f"조건이 추가되었습니다: {ticker} / {alert_type}")

    # ── [구역 2] 조건 점검 ──────────────────────────
    if st.button("조건 점검", type="primary", disabled=not st.session_state["alerts"]):
        _run_checks()

    # ── [구역 3] 조건 목록 ──────────────────────────
    alerts = st.session_state["alerts"]
    if not alerts:
        st.info("등록된 알림 조건이 없습니다.")
    else:
        results = st.session_state.get("alert_results", {})
        rows = []
        for idx, alert in enumerate(alerts):
            res = results.get(str(idx))
            status = (
                _STATUS_LABEL.get(res["status"], res["status"])
                if res
                else "❓ 미점검"
            )
            rows.append(
                {
                    "종목": alert["ticker"],
                    "조건 유형": alert["type"],
                    "목표가": (
                        f"{alert['target_price']:,.0f}"
                        if alert["target_price"] is not None
                        else "-"
                    ),
                    "등록 시각": alert["added_at"],
                    "상태": status,
                }
            )
        st.dataframe(
            pd.DataFrame(rows), width="stretch", hide_index=True
        )

        if st.button("전체 삭제"):
            st.session_state["alerts"] = []
            st.session_state["alert_results"] = {}
            st.rerun()

    # ── [구역 4] 하단 안내 ──────────────────────────
    st.caption(
        "※ 실시간 알림이 아닌 점검 시점 기준입니다. "
        "'조건 점검' 버튼을 눌러 확인하세요."
    )

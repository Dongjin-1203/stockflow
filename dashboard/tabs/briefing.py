"""탭 3 — AI 브리핑 (OpenAI).

시장 전체 브리핑 + 관심 종목 공시 요약을 생성한다.
API 키가 없으면 llm_client가 에러 메시지 문자열을 반환하며, 그대로 표시한다(graceful).
"""
from __future__ import annotations

import os
from datetime import datetime

import streamlit as st

from utils.dart_client import get_corp_code, get_recent_disclosures
from utils.ecos_client import get_latest_base_rate, get_treasury_3y
from utils.fdr_client import get_latest_price
from utils.fng_client import get_fng
from utils.llm_client import generate_disclosure_summary, generate_market_briefing
from utils.stockflow_client import get_predictions

# 종목 코드 → 회사명 매핑 (DART 조회용)
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


def _collect_market_data() -> dict:
    """시장 데이터 수집. 실패 항목은 None으로 둔다(llm_client가 '미수신' 처리)."""
    kospi = get_latest_price("KS11")
    kosdaq = get_latest_price("KQ11")
    usd_krw = get_latest_price("USD/KRW")
    fng = get_fng()
    base_rate = get_latest_base_rate()

    treasury_df = get_treasury_3y()
    treasury_3y = None
    if treasury_df is not None and not treasury_df.empty:
        treasury_3y = float(treasury_df.sort_values("date").iloc[-1]["value"])

    # StockFlow 퀀트 모델의 다음 거래일 등락 예측 (관심 종목 기준, graceful)
    selected_tickers = st.session_state.get("selected_tickers", [])
    prediction = get_predictions(selected_tickers) if selected_tickers else {}

    return {
        "kospi": (
            {"price": kospi["price"], "change_pct": kospi["change_pct"]}
            if kospi
            else None
        ),
        "kosdaq": (
            {"price": kosdaq["price"], "change_pct": kosdaq["change_pct"]}
            if kosdaq
            else None
        ),
        "usd_krw": (
            {"price": usd_krw["price"], "change": usd_krw["change_pct"]}
            if usd_krw
            else None
        ),
        "fng": (
            {
                "value": fng["value"],
                "label": fng["label"],
                "prev_value": fng["prev_value"],
            }
            if fng
            else None
        ),
        "base_rate": (
            {"rate": base_rate["rate"], "direction": base_rate["direction"]}
            if base_rate
            else None
        ),
        "treasury_3y": treasury_3y,
        "prediction": prediction,
        "date": datetime.now().strftime("%Y-%m-%d"),
    }


def _run_briefing() -> None:
    """시장 데이터 수집 + 브리핑 생성 → session_state 저장."""
    with st.spinner("시장 데이터 수집 중..."):
        market_data = _collect_market_data()
        st.session_state["market_briefing"] = generate_market_briefing(market_data)


def _render_market_briefing() -> None:
    """[구역 1] 시장 전체 브리핑."""
    st.subheader("📋 오늘의 시장 브리핑")

    # 세션 최초 진입 시 자동 1회 생성 (OpenAI 키가 있을 때만; 키 없으면 안내문 유지)
    if "market_briefing" not in st.session_state and os.getenv("OPENAI_API_KEY"):
        _run_briefing()

    if st.button("브리핑 생성", type="primary"):
        _run_briefing()

    st.markdown(
        st.session_state.get("market_briefing", "버튼을 눌러 브리핑을 생성하세요.")
    )
    st.caption(f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")


def _render_disclosure_summary() -> None:
    """[구역 2] 관심 종목 공시 요약."""
    st.subheader("🔍 관심 종목 공시 요약")

    selected_tickers = st.session_state.get("selected_tickers", [])
    if not selected_tickers:
        st.info("사이드바에서 관심 종목 코드를 입력하세요.")
        return

    dart_key = os.getenv("DART_API_KEY")

    for ticker in selected_tickers:
        corp_name = TICKER_TO_NAME.get(ticker, ticker)
        with st.expander(f"{corp_name} ({ticker})"):
            if not dart_key:
                st.info("DART API 키가 필요합니다.")
                continue

            if st.button("요약 생성", key=f"btn_summary_{ticker}"):
                with st.spinner("공시 수집·요약 중..."):
                    corp_code = get_corp_code(corp_name)
                    if corp_code is None:
                        st.session_state[f"summary_{ticker}"] = (
                            f"'{corp_name}'의 고유번호를 찾지 못했습니다."
                        )
                    else:
                        disclosures = get_recent_disclosures(corp_code, limit=3)
                        if not disclosures:
                            st.session_state[f"summary_{ticker}"] = "최근 90일 공시 없음"
                        else:
                            st.session_state[f"summary_{ticker}"] = (
                                generate_disclosure_summary(corp_name, disclosures)
                            )

            summary = st.session_state.get(f"summary_{ticker}")
            if summary:
                st.markdown(summary)
            else:
                st.caption("‘요약 생성’ 버튼을 눌러 최근 공시를 요약하세요.")


def render() -> None:
    st.info("💡 아래 브리핑은 실시간 시장 데이터를 AI가 자동 분석한 결과입니다.")
    _render_market_briefing()
    st.divider()
    _render_disclosure_summary()

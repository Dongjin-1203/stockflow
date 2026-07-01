"""금융 시장 인텔리전스 대시보드 — 엔트리포인트.

사이드바 설정 + 4개 탭(시장 현황 / 공시 탐색 / AI 브리핑 / 알림 조건) 라우팅.
"""
from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv

import streamlit as st

# .env 로드 (utils 모듈이 os.getenv를 import 시점에 읽으므로 가장 먼저 실행)
load_dotenv()

from tabs import alert, briefing, dart, market  # noqa: E402

st.set_page_config(
    page_title="금융 시장 인텔리전스 대시보드",
    page_icon="📊",
    layout="wide",
)

# ── 사이드바 ─────────────────────────────────────
st.sidebar.title("⚙️ 설정")

DEFAULT_TICKERS = ["005930", "000660", "035420"]  # 삼성전자, SK하이닉스, NAVER
ticker_input = st.sidebar.text_input(
    "관심 종목 코드 (쉼표 구분)",
    value=", ".join(DEFAULT_TICKERS),
)
selected_tickers = [t.strip() for t in ticker_input.split(",") if t.strip()]
st.session_state["selected_tickers"] = selected_tickers

period_days = st.sidebar.selectbox("조회 기간", [30, 60, 90, 180], index=2)
st.session_state["period_days"] = period_days

auto_refresh = st.sidebar.toggle("자동 갱신 (5분)", value=False)
if auto_refresh:
    st.sidebar.info("⏱ 5분 후 자동 갱신됩니다.")

st.sidebar.markdown("---")
st.sidebar.caption("데이터: FDR · DART · ECOS · Alternative.me")
st.sidebar.caption(f"브리핑: {os.getenv('OPENAI_MODEL', 'gpt-5-mini')}")

# ── 본문 ─────────────────────────────────────────
st.title("📊 금융 시장 인텔리전스 대시보드")
st.caption(
    f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    "  |  데이터 지연: 최대 15~20분"
)

tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 시장 현황", "📰 공시 탐색", "🤖 AI 브리핑", "🔔 알림 조건"]
)
with tab1:
    try:
        market.render()
    except Exception as e:  # noqa: BLE001
        st.error(f"탭 렌더링 중 오류가 발생했습니다: {e}")
with tab2:
    try:
        dart.render()
    except Exception as e:  # noqa: BLE001
        st.error(f"탭 렌더링 중 오류가 발생했습니다: {e}")
with tab3:
    try:
        briefing.render()
    except Exception as e:  # noqa: BLE001
        st.error(f"탭 렌더링 중 오류가 발생했습니다: {e}")
with tab4:
    try:
        alert.render()
    except Exception as e:  # noqa: BLE001
        st.error(f"탭 렌더링 중 오류가 발생했습니다: {e}")

# ── 자동 갱신 ────────────────────────────────────
if auto_refresh:
    import time

    time.sleep(300)
    st.rerun()

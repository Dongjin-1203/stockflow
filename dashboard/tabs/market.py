"""탭 1 — 시장 현황.

상단 지표바 / 공포·탐욕 지수 / 관심 종목 차트 / 거시지표 4개 구역으로 구성.
데이터 로딩 실패 시 빈 화면 대신 안내 문구를 출력한다.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from utils.ecos_client import get_base_rate, get_treasury_3y
from utils.fdr_client import get_latest_price, get_stock
from utils.fng_client import get_fng

# 공포·탐욕 게이지 구간 색상
_FNG_STEPS = [
    {"range": [0, 24], "color": "#d62728"},   # 극단적 공포
    {"range": [25, 44], "color": "#ff7f0e"},  # 공포
    {"range": [45, 55], "color": "#bcbd22"},  # 중립
    {"range": [56, 74], "color": "#2ca02c"},  # 탐욕
    {"range": [75, 100], "color": "#1f77b4"}, # 극단적 탐욕
]


def _render_indicator_bar() -> None:
    """[구역 1] 상단 지표바 — 코스피 / 코스닥 / 원달러 환율."""
    st.subheader("📈 주요 지표")
    col1, col2, col3 = st.columns(3)

    targets = [
        (col1, "코스피", "KS11", "pct"),
        (col2, "코스닥", "KQ11", "pct"),
        (col3, "원/달러 환율", "USD/KRW", "pct"),
    ]
    for col, label, symbol, _kind in targets:
        with col:
            data = get_latest_price(symbol)
            if data is None:
                st.metric(label, "—", "데이터 없음")
                st.caption("⚠️ 불러오기 실패")
                continue

            change = data["change_pct"]
            delta_color = "normal" if change >= 0 else "inverse"
            st.metric(
                label,
                f"{data['price']:,.2f}",
                f"{change:+.2f}%",
                delta_color=delta_color,
            )
            st.caption(f"기준일 {data['date']}")


def _render_fng() -> None:
    """[구역 2] 공포·탐욕 지수 — 게이지 + 설명."""
    st.subheader("😨 공포·탐욕 지수")
    fng = get_fng()
    if fng is None:
        st.warning("⚠️ 공포·탐욕 지수를 불러오지 못했습니다.")
        return

    col_gauge, col_desc = st.columns([2, 1])

    with col_gauge:
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=fng["value"],
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "rgba(0,0,0,0.6)"},
                    "steps": _FNG_STEPS,
                },
                domain={"x": [0, 1], "y": [0, 1]},
            )
        )
        fig.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=10))
        st.plotly_chart(fig, width="stretch")

    with col_desc:
        st.metric("현재 지수", f"{fng['value']}", fng["label"])
        diff = fng["value"] - fng["prev_value"]
        arrow = "🔺 상승" if diff > 0 else ("🔻 하락" if diff < 0 else "➖ 보합")
        st.write(
            f"**전주 대비:** {arrow} ({diff:+d}p)\n\n"
            f"이전: {fng['prev_value']} ({fng['prev_label']})"
        )


def _render_watchlist() -> None:
    """[구역 3] 관심 종목 차트 — 종목별 탭으로 표시."""
    st.subheader("⭐ 관심 종목")
    tickers = st.session_state.get("selected_tickers", [])
    period_days = st.session_state.get("period_days", 90)

    if not tickers:
        st.info("사이드바에서 관심 종목 코드를 입력하세요.")
        return

    stock_tabs = st.tabs(tickers)
    for tab, ticker in zip(stock_tabs, tickers):
        with tab:
            df = get_stock(ticker, period_days)
            if df is None or df.empty:
                st.warning(f"⚠️ {ticker} 시세를 불러오지 못했습니다.")
                continue

            fig = go.Figure(
                go.Scatter(
                    x=df["Date"],
                    y=df["Close"],
                    mode="lines",
                    line=dict(color="#E63946", width=2),
                    name="종가",
                )
            )
            fig.update_layout(
                title=f"{ticker} 주가 추이",
                xaxis_title="날짜",
                yaxis_title="종가",
                height=360,
                margin=dict(l=20, r=20, t=50, b=20),
            )
            st.plotly_chart(fig, width="stretch")


def _macro_line_chart(df, title: str, color: str) -> go.Figure:
    """거시지표용 선 차트 생성 (df: date, value)."""
    fig = go.Figure(
        go.Scatter(
            x=df["date"],
            y=df["value"],
            mode="lines+markers",
            line=dict(color=color, width=2),
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="기간",
        yaxis_title="%",
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def _render_macro() -> None:
    """[구역 4] 거시지표 — 기준금리 / 국고채 3년."""
    st.subheader("🏦 거시지표")
    col_rate, col_treasury = st.columns(2)

    with col_rate:
        df = get_base_rate()
        if df is None or df.empty:
            st.info("기준금리 데이터 로딩 중...")
        else:
            df = df.sort_values("date")
            latest = df.iloc[-1]["value"]
            st.metric("기준금리 (최신)", f"{latest:.2f}%")
            st.plotly_chart(
                _macro_line_chart(df, "기준금리 추이", "#1f77b4"),
                width="stretch",
            )

    with col_treasury:
        df = get_treasury_3y()
        if df is None or df.empty:
            st.info("국고채 3년 데이터 로딩 중...")
        else:
            df = df.sort_values("date")
            latest = df.iloc[-1]["value"]
            st.metric("국고채 3년 (최신)", f"{latest:.2f}%")
            st.plotly_chart(
                _macro_line_chart(df, "국고채 3년 추이", "#2ca02c"),
                width="stretch",
            )


def render() -> None:
    """탭 1 전체 렌더링."""
    _render_indicator_bar()
    st.divider()
    _render_fng()
    st.divider()
    _render_watchlist()
    st.divider()
    _render_macro()

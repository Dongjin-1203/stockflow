"""탭 2 — 공시 탐색 (DART OpenAPI).

관심 종목의 전자공시를 필터링해 테이블로 표시한다.
DART API 키가 없으면 graceful하게 안내 문구를 출력한다.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from utils.dart_client import get_corp_code, get_disclosures

# 종목 코드 → 회사명 매핑 (없으면 코드 그대로 사용)
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

# 공시 유형 옵션 (라벨, pblntf_ty)
PBLNTF_OPTIONS = [
    ("전체", "A"),
    ("정기공시", "A001"),
    ("수시공시", "B"),
    ("자율공시", "F"),
]


def render() -> None:
    st.subheader("📰 공시 탐색")

    selected_tickers = st.session_state.get("selected_tickers", [])
    if not selected_tickers:
        st.info("사이드바에서 관심 종목 코드를 입력하세요.")
        return

    # ── [구역 1] 필터 ───────────────────────────────
    col_stock, col_date, col_type = st.columns(3)

    with col_stock:
        ticker = st.selectbox(
            "종목 선택",
            selected_tickers,
            format_func=lambda t: f"{TICKER_TO_NAME.get(t, t)} ({t})",
        )

    with col_date:
        today = date.today()
        date_range = st.date_input(
            "조회 기간",
            value=(today - timedelta(days=90), today),
        )

    with col_type:
        type_label = st.selectbox(
            "공시 유형",
            [label for label, _ in PBLNTF_OPTIONS],
        )
        pblntf_ty = dict(PBLNTF_OPTIONS)[type_label]

    # 날짜 범위 정규화 (단일 선택 시 방어)
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        bgn_date, end_date = date_range
    else:
        bgn_date, end_date = today - timedelta(days=90), today
    bgn_de = bgn_date.strftime("%Y%m%d")
    end_de = end_date.strftime("%Y%m%d")

    # ── [구역 2] 공시 목록 ──────────────────────────
    company_name = TICKER_TO_NAME.get(ticker, ticker)

    # 키 미설정 시 명확히 안내 (호출 전 선제 처리)
    if not os.getenv("DART_API_KEY"):
        st.warning(
            "DART API 키가 설정되지 않았습니다. "
            ".env 파일에 DART_API_KEY를 입력해주세요."
        )
        st.caption("출처: 금융감독원 전자공시시스템 (DART)")
        return

    with st.spinner("공시 조회 중..."):
        corp_code = get_corp_code(company_name)
        if corp_code is None:
            st.warning(
                f"'{company_name}'의 고유번호(corp_code)를 찾지 못했습니다. "
                "회사명 또는 DART API 키를 확인해주세요."
            )
            st.caption("출처: 금융감독원 전자공시시스템 (DART)")
            return

        disclosures = get_disclosures(corp_code, bgn_de, end_de, pblntf_ty)

    if not disclosures:
        st.info("조회된 공시가 없습니다.")
    else:
        df = pd.DataFrame(
            {
                "접수일자": [d["rcept_dt"] for d in disclosures],
                "보고서명": [d["report_nm"] for d in disclosures],
                "원문링크": [d["url"] for d in disclosures],
            }
        )
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "원문링크": st.column_config.LinkColumn(
                    "원문링크", display_text="📄 원문 보기"
                ),
            },
        )
        st.caption(f"총 {len(disclosures)}건 조회됨")

    # ── [구역 3] 하단 안내 ──────────────────────────
    st.caption("출처: 금융감독원 전자공시시스템 (DART)")

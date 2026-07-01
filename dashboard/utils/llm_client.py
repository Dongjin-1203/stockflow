"""Anthropic(Claude) 기반 시장 브리핑/공시 요약 클라이언트.

knowledge/ 디렉토리의 프롬프트·지식 파일을 읽어 시스템 프롬프트를 구성한다.
파일이 없어도 동작하도록 기본값을 제공하며, 호출 실패 시 에러 메시지 문자열을 반환한다.

환경변수:
    ANTHROPIC_API_KEY   Claude API 키
    ANTHROPIC_MODEL     사용할 모델 (기본: claude-opus-4-8)
                        비용/지연 민감 시 claude-sonnet-4-6 또는 claude-haiku-4-5 권장
"""
from __future__ import annotations

import os
from pathlib import Path

import anthropic

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

# 브리핑은 짧은 산문, 공시 요약은 더 짧음 — 응답 상한(필수 파라미터)
_BRIEFING_MAX_TOKENS = 2048
_SUMMARY_MAX_TOKENS = 512

_DISCLAIMER = "\n\n---\n※ 본 브리핑은 AI가 생성한 투자 참고 자료이며, 투자 권유가 아닙니다. 투자 판단과 책임은 투자자 본인에게 있습니다."

_DEFAULT_SYSTEM_PROMPT = """당신은 한국 금융시장 전문 애널리스트입니다.
제공된 시장 데이터를 바탕으로 간결하고 객관적인 한국어 시장 브리핑을 작성하세요.
- 과장된 표현이나 단정적 예측을 피하고 데이터에 근거해 서술합니다.
- 코스피/코스닥/환율/공포탐욕지수/금리 흐름을 종합해 시장 분위기를 요약합니다.
- 마크다운 형식으로 핵심을 구조화합니다.
- 최종 브리핑 본문만 출력하고, 사고 과정이나 서두("알겠습니다" 등)는 쓰지 않습니다."""


def _get_client() -> anthropic.Anthropic:
    """Anthropic 클라이언트 생성 (호출 시점 초기화).

    API 키가 없으면 요청 시 예외가 발생하며, 호출 함수에서 처리한다.
    """
    return anthropic.Anthropic()


def _text_from(response) -> str:
    """Claude 응답에서 첫 text 블록을 추출."""
    return next((b.text for b in response.content if b.type == "text"), "").strip()


def _read(filename: str) -> str:
    """knowledge/ 내 파일 읽기. 없으면 빈 문자열."""
    try:
        path = KNOWLEDGE_DIR / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[llm_client._read] {filename} 읽기 실패: {e}")
    return ""


def load_knowledge() -> str:
    """지식 베이스 3종을 순서대로 읽어 합치기. 없으면 빈 문자열."""
    parts = [
        _read("kb_market_indicators.md"),
        _read("kb_sector_mapping.md"),
        _read("kb_signal_rules.md"),
    ]
    return "\n\n".join(p for p in parts if p)


def build_system_prompt() -> str:
    """system_prompt_briefing.md + 지식 베이스 결합. 파일 없으면 기본 프롬프트 사용."""
    base = _read("system_prompt_briefing.md") or _DEFAULT_SYSTEM_PROMPT
    knowledge = load_knowledge()
    if knowledge:
        return f"{base}\n\n# 참고 지식\n{knowledge}"
    return base


def _format_market_data(market_data: dict) -> str:
    """market_data dict를 LLM 입력용 텍스트 블록으로 구성.

    output_schema.md에 입력 템플릿이 있으면 그 형식을 함께 제공한다.
    """
    kospi = market_data.get("kospi") or {}
    kosdaq = market_data.get("kosdaq") or {}
    usd_krw = market_data.get("usd_krw") or {}
    fng = market_data.get("fng") or {}
    base_rate = market_data.get("base_rate") or {}
    treasury_3y = market_data.get("treasury_3y")
    prediction = market_data.get("prediction") or {}
    date = market_data.get("date", "")

    def _num(v) -> str:
        return "미수신" if v is None else f"{v}"

    lines = [
        f"기준일자: {date or '미수신'}",
        f"코스피: 종가 {_num(kospi.get('price'))}, 등락률 {_num(kospi.get('change_pct'))}%",
        f"코스닥: 종가 {_num(kosdaq.get('price'))}, 등락률 {_num(kosdaq.get('change_pct'))}%",
        f"원/달러 환율: {_num(usd_krw.get('price'))}, 변동 {_num(usd_krw.get('change'))}",
        f"공포·탐욕지수: {_num(fng.get('value'))} ({fng.get('label', '미수신')}), "
        f"직전 {_num(fng.get('prev_value'))}",
        f"기준금리: {_num(base_rate.get('rate'))}% ({base_rate.get('direction', '미수신')})",
        f"국고채 3년: {_num(treasury_3y)}%",
    ]
    # StockFlow 퀀트 모델의 다음 거래일 등락 예측(있을 때만)
    if prediction:
        preds = ", ".join(
            f"{tk}: {'상승' if p.get('prediction') == 1 else '하락'}"
            f"(상승확률 {p.get('probability_up')})"
            for tk, p in prediction.items()
        )
        lines.append(f"퀀트 모델 다음 거래일 예측 — {preds}")
    data_block = "\n".join(lines)

    schema = _read("output_schema.md")
    if schema:
        return f"# 출력 형식\n{schema}\n\n# 입력 데이터\n{data_block}"
    return f"# 입력 데이터\n{data_block}"


def generate_market_briefing(market_data: dict) -> str:
    """시장 데이터를 받아 AI 브리핑 생성. 실패 시 에러 메시지 문자열 반환."""
    try:
        client = _get_client()
        system_prompt = build_system_prompt()
        user_content = _format_market_data(market_data)

        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=_BRIEFING_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        text = _text_from(resp)
        if not text:
            return "⚠️ 브리핑 생성 결과가 비어 있습니다."

        # 면책 문구 강제 append
        if "투자 권유가 아닙니다" not in text and "투자 참고" not in text:
            text += _DISCLAIMER
        return text
    except Exception as e:  # noqa: BLE001
        return f"⚠️ 브리핑 생성 중 오류가 발생했습니다: {e}"


def generate_disclosure_summary(corp_name: str, disclosures: list[dict]) -> str:
    """종목명 + 최근 공시 목록을 받아 한 문단 요약 생성. 실패 시 에러 메시지 반환."""
    try:
        if not disclosures:
            return f"{corp_name}: 최근 90일 공시가 없습니다."

        titles = "\n".join(
            f"- {d.get('rcept_dt', '')} {d.get('report_nm', '')}"
            for d in disclosures[:3]
        )
        client = _get_client()
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=_SUMMARY_MAX_TOKENS,
            system=(
                "당신은 한국 기업 공시 분석가입니다. "
                "주어진 최근 공시 제목들을 바탕으로 핵심 내용을 한 문단(2~3문장)으로 "
                "객관적으로 요약하세요. 추측은 피하고 제목에 근거해 서술합니다. "
                "요약 본문만 출력합니다."
            ),
            messages=[
                {"role": "user", "content": f"종목명: {corp_name}\n최근 공시:\n{titles}"},
            ],
        )
        text = _text_from(resp)
        return text or f"{corp_name}: 공시 요약 생성 결과가 비어 있습니다."
    except Exception as e:  # noqa: BLE001
        return f"⚠️ {corp_name} 공시 요약 중 오류가 발생했습니다: {e}"

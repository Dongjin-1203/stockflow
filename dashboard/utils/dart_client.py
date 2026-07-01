"""DART OpenAPI(전자공시) 클라이언트.

공식 REST API: https://opendart.fss.or.kr/api/
모든 함수는 실패 시 None 또는 빈 리스트를 반환해 앱이 죽지 않도록 한다.
"""
from __future__ import annotations

import io
import os
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta

import requests
import streamlit as st

DART_API_KEY = os.getenv("DART_API_KEY")

BASE_URL = "https://opendart.fss.or.kr/api"
CORP_CODE_URL = f"{BASE_URL}/corpCode.xml"
DISCLOSURE_URL = f"{BASE_URL}/list.json"

_TIMEOUT = 10


@st.cache_data(ttl=86400)
def _load_corp_code_map() -> dict[str, str]:
    """corpCode.xml(zip)을 받아 {회사명: corp_code} 매핑 생성.

    실패 시 빈 dict 반환.
    """
    if not DART_API_KEY:
        print("[dart_client] DART_API_KEY 미설정")
        return {}
    try:
        resp = requests.get(
            CORP_CODE_URL, params={"crtfc_key": DART_API_KEY}, timeout=_TIMEOUT
        )
        resp.raise_for_status()

        # 응답이 에러 JSON/XML일 수 있으므로 zip 여부 확인
        if not resp.content[:2] == b"PK":
            print(f"[dart_client] corpCode 응답이 zip 아님: {resp.content[:200]!r}")
            return {}

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_name = zf.namelist()[0]
            xml_bytes = zf.read(xml_name)

        root = ET.fromstring(xml_bytes)
        mapping: dict[str, str] = {}
        for item in root.iter("list"):
            name = (item.findtext("corp_name") or "").strip()
            code = (item.findtext("corp_code") or "").strip()
            # 상장사 우선 (stock_code 존재). 동일 회사명은 첫 항목 유지.
            if name and code and name not in mapping:
                mapping[name] = code
        return mapping
    except Exception as e:  # noqa: BLE001
        print(f"[dart_client._load_corp_code_map] 실패: {e}")
        return {}


@st.cache_data(ttl=86400)
def get_corp_code(company_name: str) -> str | None:
    """회사명으로 corp_code(8자리) 조회. 없으면 None."""
    try:
        mapping = _load_corp_code_map()
        if not mapping:
            return None
        name = company_name.strip()
        if name in mapping:
            return mapping[name]
        # 부분 일치 보조 탐색 (완전일치 우선)
        for corp_name, code in mapping.items():
            if name and name in corp_name:
                return code
        return None
    except Exception as e:  # noqa: BLE001
        print(f"[dart_client.get_corp_code] {company_name} 실패: {e}")
        return None


@st.cache_data(ttl=600)
def get_disclosures(
    corp_code: str, bgn_de: str, end_de: str, pblntf_ty: str = "A"
) -> list[dict]:
    """공시 목록 조회.

    bgn_de/end_de 형식: YYYYMMDD
    반환: [{"rcept_dt", "report_nm", "rcept_no", "url"}, ...]
    실패 또는 결과 없음 시 빈 리스트.
    """
    if not DART_API_KEY or not corp_code:
        return []
    try:
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "pblntf_ty": pblntf_ty,
            "page_no": 1,
            "page_count": 100,
        }
        resp = requests.get(DISCLOSURE_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # status '000'만 정상. '013'(조회 데이터 없음) 등은 빈 리스트.
        if data.get("status") != "000":
            if data.get("status") != "013":
                print(f"[dart_client.get_disclosures] status={data.get('status')} {data.get('message')}")
            return []

        results: list[dict] = []
        for item in data.get("list", []):
            rcept_no = item.get("rcept_no", "")
            results.append(
                {
                    "rcept_dt": item.get("rcept_dt", ""),
                    "report_nm": item.get("report_nm", ""),
                    "rcept_no": rcept_no,
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                }
            )
        return results
    except Exception as e:  # noqa: BLE001
        print(f"[dart_client.get_disclosures] {corp_code} 실패: {e}")
        return []


def get_recent_disclosures(corp_code: str, limit: int = 20) -> list[dict]:
    """최근 limit건 공시 반환 (조회 시작일 = 90일 전, 전체 유형)."""
    try:
        end = datetime.now()
        bgn = end - timedelta(days=90)
        disclosures = get_disclosures(
            corp_code,
            bgn.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            pblntf_ty="A",
        )
        # list.json은 최신순 반환 → 상위 limit건
        return disclosures[:limit]
    except Exception as e:  # noqa: BLE001
        print(f"[dart_client.get_recent_disclosures] {corp_code} 실패: {e}")
        return []

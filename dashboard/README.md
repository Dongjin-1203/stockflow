# 금융 시장 인텔리전스 대시보드

강사 시연용 Streamlit 대시보드.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # .env 편집 후 API 키 입력
streamlit run app.py
```

## 구성

* 탭 1: 시장 현황 (코스피/코스닥/환율/공탐지수/거시지표)
* 탭 2: 공시 탐색 (DART OpenAPI)
* 탭 3: AI 브리핑 (OpenAI · StockFlow 예측 연동)
* 탭 4: 알림 조건

## 배포

* Cloud Run: `bash deploy.sh`
* Streamlit Cloud: GitHub 연동 후 share.streamlit.io에서 배포

## Streamlit Cloud 배포
1. 이 레포를 GitHub에 push (.env 제외)
2. share.streamlit.io → New app → 레포 선택
3. Main file path: app.py
4. Advanced settings → Python version: 3.11
5. Secrets 탭에 .env 내용 붙여넣기
6. Deploy

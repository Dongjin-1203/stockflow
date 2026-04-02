# StockFlow

주식 가격 예측 ML 파이프라인 — 데이터 수집부터 모델 서빙까지 end-to-end 자동화.

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 목적 | 한국/미국 주식 종목의 단기 가격 방향성 예측 |
| 예측 대상 | 다음 거래일 종가 등락 방향 (binary classification) |
| 업데이트 주기 | 매일 장 마감 후 Airflow DAG 자동 실행 |

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 데이터 수집 | `yfinance`, `pandas` |
| 피처 엔지니어링 | `ta` (technical analysis), `scikit-learn` |
| 모델 학습 | `LightGBM`, `XGBoost` |
| 실험 추적 | `MLflow` |
| 오케스트레이션 | `Apache Airflow 2.9` |
| 오브젝트 스토리지 | `MinIO` (로컬) / `AWS S3` (프로덕션) |
| 서빙 | `FastAPI` |
| 데이터베이스 | `PostgreSQL 16` |
| 컨테이너 | `Docker`, `docker-compose` |

## 디렉토리 구조

```
stockflow/
├── dags/              # Airflow DAG 정의
│   └── pipeline_dag.py
├── models/            # 직렬화된 모델 파일 (gitignore)
├── notebooks/         # EDA, 실험용 Jupyter 노트북
├── src/
│   ├── data/          # 데이터 수집·저장 모듈
│   │   ├── __init__.py
│   │   └── fetcher.py
│   ├── features/      # 피처 엔지니어링 모듈
│   │   ├── __init__.py
│   │   └── engineer.py
│   └── serving/       # FastAPI 앱
│       ├── __init__.py
│       └── main.py
├── tests/             # pytest 테스트
├── docker/            # 서비스별 Dockerfile
│   └── Dockerfile.api
├── .env.example       # 환경변수 템플릿
├── .gitignore
├── requirements.txt
├── docker-compose.yml
└── CLAUDE.md
```

## 주요 명령어

### 환경 설정

```bash
# 환경변수 파일 복사
cp .env.example .env
# .env 편집 후 실제 값 입력

# Python 가상환경 (로컬 개발)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Docker 서비스 실행

```bash
# 전체 스택 기동 (최초)
docker-compose up -d

# 특정 서비스만 재시작
docker-compose restart airflow-scheduler

# 로그 확인
docker-compose logs -f airflow-webserver

# 종료
docker-compose down

# 볼륨 포함 완전 삭제
docker-compose down -v
```

### 서비스 URL

| 서비스 | URL | 기본 계정 |
|--------|-----|-----------|
| Airflow UI | http://localhost:8080 | admin / admin |
| MLflow UI | http://localhost:5000 | — |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| FastAPI docs | http://localhost:8000/docs | — |

### 파이프라인 수동 실행

```bash
# DAG 트리거
docker-compose exec airflow-webserver airflow dags trigger stockflow_pipeline

# 특정 태스크만 실행
docker-compose exec airflow-webserver airflow tasks run stockflow_pipeline fetch_data <execution_date>
```

### 테스트

```bash
pytest tests/ -v
pytest tests/ -v --cov=src --cov-report=term-missing
```

### 코드 품질

```bash
black src/ tests/
ruff check src/ tests/ --fix
```

## 데이터 흐름

```
yfinance API
    │
    ▼
src/data/fetcher.py   ──→  MinIO (raw/)
    │
    ▼
src/features/engineer.py  ──→  MinIO (processed/)
    │
    ▼
LightGBM 학습  ──→  MLflow (실험 추적)  ──→  모델 등록
    │
    ▼
src/serving/main.py  (FastAPI)  ──→  /predict 엔드포인트
```

## 환경변수 주요 항목

| 변수 | 설명 |
|------|------|
| `MLFLOW_TRACKING_URI` | MLflow 서버 주소 |
| `MLFLOW_S3_ENDPOINT_URL` | MinIO/S3 엔드포인트 |
| `AIRFLOW__CORE__FERNET_KEY` | Airflow 암호화 키 (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) |
| `AWS_ACCESS_KEY_ID` | MinIO 또는 AWS 액세스 키 |
| `AWS_SECRET_ACCESS_KEY` | MinIO 또는 AWS 시크릿 키 |

## 브랜치 전략

| 브랜치 | 설명 |
|--------|------|
| `main` | 안정 버전 (직접 push 금지) |
| `develop` | 통합 브랜치 |
| `feature/phase-{n}-{작업명}` | 기능 개발 |

## 작업 흐름

```
feature → develop (PR) → main (PR)
```

## 현재 Phase

| Phase | 상태 | 내용 |
|-------|------|------|
| Phase 1 | 완료 | Docker Compose 로컬 스택 (Airflow + MLflow + MinIO + PostgreSQL) |

## PR 흐름 기준

### 브랜치 merge 규칙
- feature/* → develop : Phase 단위 완료 시
- develop → main : 마일스톤 단위 완료 시 (직접 push 금지)

### feature → develop PR 조건
- 해당 Phase 목표 기능 정상 동작 확인
- DAG 수동 트리거 성공 확인

### develop → main PR 조건
- Phase 1~4 완료 (로컬 전체 파이프라인 end-to-end 동작)
- 또는 Phase 5 완료 (AWS 배포 완료)

### 현재 상태
- feature/phase-1-docker-setup: 작업 완료, develop PR 대기 중
- develop → main: 미개방 (Phase 4 이후 예정)

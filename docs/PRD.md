# StockFlow — Product Requirements Document (PRD)

> 본 문서는 현재 코드베이스로부터 **역설계(reverse-engineered)** 하여 작성된 제품 요구사항 정의서입니다.
> 작성일: 2026-06-28 · 대상 버전: Phase 1 (로컬 end-to-end 파이프라인 완료 시점)

---

## 1. 개요 (Overview)

StockFlow는 한국/미국 주식 종목의 **다음 거래일 종가 등락 방향(상승/하락)을 예측**하는 end-to-end 머신러닝 파이프라인이다. 데이터 수집부터 모델 서빙까지 전 과정을 컨테이너 기반으로 자동화하여, 매일 장 마감 후 최신 데이터로 모델을 재학습·평가·배포한다.

| 항목 | 내용 |
|------|------|
| 제품명 | StockFlow |
| 목적 | 주식 단기 가격 방향성 예측 ML 파이프라인의 자동화 |
| 예측 대상 | 다음 거래일 종가 등락 방향 (binary classification: 1=상승, 0=하락) |
| 업데이트 주기 | 매일 장 마감 후 (Airflow DAG 자동 실행, 평일 18:00) |
| 배포 형태 | Docker Compose 로컬 스택 (→ 향후 AWS) |

---

## 2. 배경 및 문제 정의 (Background & Problem)

개인 투자자/퀀트 연구자가 단기 가격 방향성에 대한 정량적 시그널을 얻으려면, 데이터 수집·피처 생성·모델 학습·서빙을 매번 수동으로 반복해야 한다. 이 과정은 재현이 어렵고, 실험 추적이 안 되며, 최신 데이터 반영이 늦다.

**StockFlow가 해결하는 것:**
- 데이터 수집 → 피처 → 학습 → 평가 → 서빙의 **완전 자동화**
- 모든 모델 실험의 **추적 및 버전 관리** (MLflow)
- 신규 모델이 기존 모델보다 **나을 때만 자동 승격**되는 안전한 배포
- 로컬과 프로덕션(AWS)에서 **동일하게 동작**하는 인프라

---

## 3. 목표 및 비목표 (Goals / Non-Goals)

### 목표
- G1. yfinance 기반 OHLCV 데이터를 자동 수집하여 오브젝트 스토리지에 적재
- G2. 기술적 분석 지표(trend/momentum/volatility/volume)를 피처로 생성
- G3. LightGBM 이진 분류 모델을 시계열 누수 없이 학습하고 MLflow에 기록
- G4. 신규 모델을 현 Production 모델과 비교하여 우수할 때만 자동 승격
- G5. FastAPI를 통해 등록된 Production 모델로 실시간 예측 제공
- G6. 전 과정을 Airflow DAG로 일일 자동 실행

### 비목표 (현 단계에서 다루지 않음)
- NG1. 실제 매매 주문 실행/브로커 연동
- NG2. 종가 외 가격대(고가/저가) 또는 회귀(연속값) 예측
- NG3. 분 단위/실시간 스트리밍 예측
- NG4. 투자 자문/수익 보장 (예측 시그널 제공에 한정)
- NG5. 멀티 유저 인증/권한 관리

---

## 4. 사용자 및 페르소나 (Users)

| 페르소나 | 니즈 | 사용 방식 |
|----------|------|-----------|
| 퀀트 연구자 | 재현 가능한 실험 환경, 모델 성능 추적 | MLflow UI, DAG 트리거 |
| 개인 투자자 | 종목별 등락 방향 시그널 | FastAPI `/predict` 호출 |
| ML 엔지니어 | 파이프라인 운영·확장 | Airflow UI, Docker Compose |

---

## 5. 기능 요구사항 (Functional Requirements)

### FR-1. 데이터 수집 (`src/data/fetcher.py`)
- FR-1.1 yfinance로 단일/다중 티커의 OHLCV 데이터를 다운로드한다.
- FR-1.2 다중 수집 시 일부 티커 실패는 경고로 처리하고 나머지를 계속 수집한다.
- FR-1.3 yfinance의 MultiIndex 컬럼 응답을 단일 레벨로 평탄화한다.
- FR-1.4 데이터가 전혀 수집되지 않으면 명시적으로 실패한다 (빈 성공 금지).

### FR-2. 저장 계층 (`src/data/storage.py`)
- FR-2.1 OHLCV/피처 데이터를 Parquet 형식으로 S3 호환 스토리지에 저장·조회한다.
- FR-2.2 키 규약: `raw/{ticker}/{date}.parquet`, `processed/{ticker}/{date}.parquet`.
- FR-2.3 버킷 부재 시 자동 생성(멱등), 객체 존재 확인, 프리픽스 기반 목록 조회.
- FR-2.4 로컬(MinIO)과 프로덕션(AWS S3)에서 환경변수만으로 동일하게 동작한다.

### FR-3. 피처 엔지니어링 (`src/features/engineer.py`)
- FR-3.1 기술 지표 생성: EMA, MACD, RSI, Stochastic, Bollinger Bands, ATR, OBV.
- FR-3.2 라벨 생성: `horizon`일 후 종가 > 현재 종가이면 1, 아니면 0.
- FR-3.3 미래값이 없는 후행 `horizon`개 행은 무효화 후 제거한다 (라벨 누수 방지).
- FR-3.4 학습용 `(X, y)`를 반환하며 X에는 원본 OHLCV·target을 포함하지 않는다.

### FR-4. 모델 학습 (`src/models/train.py`)
- FR-4.1 LightGBM 이진 분류기를 학습한다.
- FR-4.2 시계열 순서를 유지하는 chronological split으로 검증한다 (look-ahead 누수 금지).
- FR-4.3 파라미터·메트릭(accuracy/f1/auc)을 MLflow에 기록한다.
- FR-4.4 학습된 모델을 MLflow Model Registry에 신규 버전으로 등록한다.

### FR-5. 모델 평가·승격 (`src/models/evaluate.py`)
- FR-5.1 신규 버전의 검증 메트릭(AUC)을 현 Production 모델과 비교한다.
- FR-5.2 Production이 없으면(콜드 스타트) 무조건 승격한다.
- FR-5.3 신규가 더 우수하면 승격하고 기존 버전은 자동 archive한다.
- FR-5.4 신규 메트릭이 NaN(단일 클래스 검증)이면 기존 모델을 유지한다.

### FR-6. 서빙 (`src/serving/main.py`)
- FR-6.1 기동 시 MLflow Registry에서 Production 모델을 로드한다.
- FR-6.2 `GET /health` — 상태 및 모델 로드 여부 반환.
- FR-6.3 `POST /predict` — 피처 dict를 받아 등락 방향과 상승 확률을 반환.
- FR-6.4 모델 미로드 시 503, 입력 스키마 불일치 시 422를 반환한다.

### FR-7. 오케스트레이션 (`dags/pipeline_dag.py`)
- FR-7.1 `fetch_data → build_features → train_model → evaluate_model` 순차 실행.
- FR-7.2 평일 18:00(KST) 스케줄 + 수동 트리거 지원.
- FR-7.3 task 실패 시 5분 간격 2회 재시도.
- FR-7.4 `train_model`은 run_id/version을 XCom으로 `evaluate_model`에 전달한다.

---

## 6. 비기능 요구사항 (Non-Functional Requirements)

| 분류 | 요구사항 |
|------|----------|
| 재현성 | 모든 의존성은 이미지에 baking, 버전 핀 고정 |
| 이식성 | 로컬(MinIO)↔프로덕션(AWS S3) 환경변수만으로 전환 |
| 데이터 정합성 | 시계열 누수 방지(학습 분할·라벨링 모두) |
| 관측성 | 모든 실험은 MLflow에 추적, Airflow UI에서 task 상태 확인 |
| 테스트 | 핵심 모듈은 mock 기반 단위 테스트로 검증 (네트워크 비의존) |
| 안전성 | 모델 승격은 성능 기준 충족 시에만 (회귀 방지) |

---

## 7. 시스템 아키텍처 (Architecture)

```
yfinance API
    │
    ▼
[fetch_data]  src/data/fetcher.py ──▶ MinIO (raw/)
    │
    ▼
[build_features]  src/features/engineer.py ──▶ MinIO (processed/)
    │
    ▼
[train_model]  src/models/train.py ──▶ MLflow (실험 추적 + 모델 등록)
    │
    ▼
[evaluate_model]  src/models/evaluate.py ──▶ MLflow (Production 승격)
    │
    ▼
src/serving/main.py (FastAPI) ──▶ /predict  (Production 모델 서빙)

오케스트레이션: Apache Airflow (LocalExecutor)
메타데이터/아티팩트: PostgreSQL 16 / MinIO (S3 호환)
```

### 기술 스택
| 레이어 | 기술 |
|--------|------|
| 데이터 수집 | yfinance, pandas |
| 피처 | ta, scikit-learn |
| 학습 | LightGBM (+ XGBoost 예정) |
| 실험 추적 | MLflow 2.13 |
| 오케스트레이션 | Apache Airflow 2.9 |
| 스토리지 | MinIO (로컬) / AWS S3 (프로덕션) |
| 서빙 | FastAPI |
| DB | PostgreSQL 16 |
| 컨테이너 | Docker, docker-compose |

---

## 8. 데이터 명세 (Data Spec)

| 단계 | 위치 | 형식 | 스키마 |
|------|------|------|--------|
| 원천 | yfinance | — | OHLCV |
| raw | `raw/{ticker}/{date}.parquet` | Parquet | Open, High, Low, Close, Volume |
| processed | `processed/{ticker}/{date}.parquet` | Parquet | 기술지표 피처 11종 + target |
| 모델 | MLflow Registry (`stockflow`) | MLflow model | LightGBM booster |

**대상 티커(기본):** `005930.KS`(삼성전자), `000660.KS`(SK하이닉스), `AAPL`, `NVDA`

**피처(11종):** ema_10, ema_30, macd, macd_signal, rsi_14, stoch_k, bb_high, bb_low, bb_width, atr, obv

---

## 9. 인터페이스 명세 (API)

### `GET /health`
```json
{ "status": "ok", "model_loaded": true }
```

### `POST /predict`
요청:
```json
{ "ticker": "AAPL", "features": { "ema_10": 185.9, "rsi_14": 52.3, "...": 0.0 } }
```
응답:
```json
{ "ticker": "AAPL", "prediction": 0, "probability_up": 0.4232 }
```

| 서비스 | URL | 계정 |
|--------|-----|------|
| Airflow UI | http://localhost:8080 | admin/admin |
| MLflow UI | http://localhost:5000 | — |
| MinIO Console | http://localhost:9001 | minioadmin/minioadmin |
| FastAPI docs | http://localhost:8000/docs | — |

---

## 10. 마일스톤 (Roadmap)

| Phase | 상태 | 내용 |
|-------|------|------|
| Phase 1 | ✅ 완료·검증 | Docker 로컬 스택 + end-to-end 파이프라인 동작 (DAG 4 task, MinIO/MLflow/서빙 실확인) |
| Phase 2 | 예정 | 학습 데이터 확대(다기간), 피처 중요도 분석, 하이퍼파라미터 튜닝 |
| Phase 3 | 예정 | 백테스팅 프레임워크, 모델 성능 모니터링·드리프트 감지 |
| Phase 4 | 예정 | 로컬 전체 파이프라인 안정화 (develop→main 마일스톤) |
| Phase 5 | 예정 | AWS 배포 (S3 + ECS/EKS + RDS) |

---

## 11. 성공 지표 (Success Metrics)

- M1. DAG 일일 자동 실행 성공률 ≥ 95%
- M2. 검증셋 기준 모델 AUC > 0.5 (랜덤 대비 우위) 지속 유지
- M3. 신규 모델 승격이 성능 기준에 의해서만 발생 (성능 회귀 0건)
- M4. `/predict` 응답 지연 < 200ms (단건)
- M5. 핵심 모듈 단위 테스트 통과율 100%

---

## 12. 리스크 및 대응 (Risks)

| 리스크 | 영향 | 대응 |
|--------|------|------|
| yfinance API 변경/단절 | 데이터 수집 실패 | 버전 핀 + fail-fast + 향후 데이터 소스 이중화 |
| 데이터 누수(look-ahead) | 과대평가된 성능 | chronological split + 라벨 후행행 제거 |
| 시장 비정상성(non-stationarity) | 예측력 저하 | 일일 재학습 + 드리프트 모니터링(Phase 3) |
| 단일 실행일 데이터 부족 | 과소학습 | 다기간 학습 데이터 확대(Phase 2) |
| 의존성 충돌 | 빌드/런타임 실패 | 이미지 baking + 버전 핀 고정 |

---

## 부록 A. 환경변수

`MLFLOW_TRACKING_URI`, `MLFLOW_S3_ENDPOINT_URL`, `MLFLOW_EXPERIMENT_NAME`, `MLFLOW_MODEL_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_DEFAULT_REGION`, `AIRFLOW__CORE__FERNET_KEY` 등 — 상세는 `.env.example` 참조.

## 부록 B. 브랜치 전략

- `main`: 안정 버전 (직접 push 금지, PR로만 병합)
- `develop`: 통합 브랜치
- `feature/phase-{n}-{작업명}`: 기능 개발
- 흐름: `feature → develop (PR) → main (PR)`

# K-PatternHunters — 고객 행동 패턴 분석 자동화 시스템

웹 앱 로그 데이터를 분석하고, 멀티 에이전트 AI 파이프라인을 통해 PowerPoint 보고서를 자동 생성하는 시스템입니다.

---

## 주요 기능

- **도메인 자동 인식** — 사용자가 도메인 설명을 입력하면 LLM이 분석 컨텍스트를 자동 생성
- **6종 병렬 분석** — 퍼널 / 코호트 / 사용자 여정 / 성과 KPI / 이상 감지 / 예측 분석을 동시 실행
- **자동 PPT 생성** — 분석 결과를 8슬라이드 PowerPoint 보고서로 자동 렌더링 (한국어)
- **비동기 처리** — Celery 기반 작업 큐로 분석 요청을 백그라운드에서 처리
- **실시간 상태 조회** — 프론트엔드에서 분석 진행 상태를 폴링으로 확인

---

## 시스템 아키텍처

```
[Vue.js 대시보드]
       │  POST /analysis/run
       ▼
[FastAPI + Celery Worker]
       │
       ▼
[LangGraph 멀티 에이전트 파이프라인]
       │
context_agent          ← 도메인 분석 컨텍스트 생성 (LLM + RAG + 웹검색)
       │
analysis_dispatcher    ← 병렬 실행 (asyncio.gather)
       ├── funnel_agent        퍼널 단계별 전환율 / 이탈률
       ├── cohort_agent        첫 구매 주차별 리텐션 코호트
       ├── journey_agent       세션 경로 분석 / 이탈 패턴
       ├── performance_agent   주간 KPI + WoW 비교
       ├── anomaly_agent       Z-score 이상 감지 + LLM 해석
       └── prediction_agent    선형 회귀 기반 다음 주 예측
              │
       insight_agent    ← 6개 분석 결과 종합 → 슬라이드별 인사이트 생성 (LLM)
              │
       ppt_agent        ← 8슬라이드 .pptx 자동 생성
              │
          [결과 반환]
```

### PPT 슬라이드 구성 (8슬라이드 고정)

| 슬라이드 | 제목 | 내용 |
|---|---|---|
| Slide 1 | Executive Summary | KPI 카드 3개 (매출/전환율/세션) + WoW 증감 |
| Slide 2 | 주요 지표 현황 | KPI 테이블 + 일별 추이 차트 |
| Slide 3 | 이상 감지 결과 | Z-score 강조 테이블 |
| Slide 4 | 사용자 흐름 분석 | 퍼널 테이블 + 전환/이탈 경로 Top 5 |
| Slide 5 | 고객 세그먼트 분석 | 디바이스/소스/신규·재방문/국가별 + 코호트 히트맵 |
| Slide 6 | 도메인 심화 분석 | e-커머스: 카테고리별 구매 분석 |
| Slide 7 | 예측 및 시사점 | 다음 주 예측값 + LLM 시사점 |
| Slide 8 | 권장 액션 | P1/P2/P3 우선순위 + 교차 분석 인사이트 |

---

## 기술 스택

| 역할 | 기술 |
|---|---|
| 프론트엔드 | Vue 3 + Vite |
| 백엔드 | FastAPI |
| AI 오케스트레이션 | LangGraph (StateGraph) |
| LLM | OpenAI GPT-4o / GPT-4o-mini |
| 비동기 작업 큐 | Celery + Redis |
| 데이터베이스 | MongoDB (motor 비동기 드라이버) |
| 벡터 DB | Qdrant (RAG) |
| PPT 생성 | python-pptx |
| 웹검색 | Tavily API |
| 컨테이너 | Docker Compose |

---

## 빠른 시작

### 사전 요구사항

- Docker & Docker Compose
- OpenAI API 키
- (선택) Tavily API 키 — 웹검색 기능 사용 시

### 1. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일에서 아래 항목을 채워주세요:

```env
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...       # 선택

MONGO_USER=admin
MONGO_PASSWORD=password
MONGO_DB=customer_behavior
MONGO_COLLECTION=raw_logs
```

### 2. 서비스 실행

```bash
docker compose up --build
```

| 서비스 | URL |
|---|---|
| 프론트엔드 | http://localhost:5173 |
| 백엔드 API | http://localhost:8000/docs |
| MongoDB UI | http://localhost:8081 |
| Qdrant 대시보드 | http://localhost:6333/dashboard |

### 3. 데이터 적재

**BigQuery에서 직접 가져오기 (GCP 서비스 계정 필요):**

```bash
docker compose run --rm ingest python export_bq.py
docker compose run --rm ingest python ingest_local.py
```

**로컬 NDJSON 파일에서 적재:**

```bash
# data/ecom-data/ 폴더에 .ndjson.gz 파일을 넣고
docker compose run --rm ingest python ingest_local.py
```

### 4. RAG 문서 적재 (선택)

```bash
docker compose run --rm backend python -m rag.ingest_docs
```

---

## 사용 방법

1. http://localhost:5173 접속
2. 분석 기준일 선택 (해당 날짜 기준으로 7일 주간 분석)
3. 도메인 설명 입력 (예: `"GA4 e-커머스 쇼핑몰"`)
4. **분석 시작** 버튼 클릭
5. 분석 완료 후 PPT 다운로드

---

## 데이터 소스

- **원본 데이터:** GA4 BigQuery `ga4_obfuscated_sample_ecommerce` 공개 샘플 데이터셋
- **기간:** 2020-12-15 ~ 2021-01-31
- **MongoDB 컬렉션 구조:**

| 컬렉션 | 건수 | 내용 |
|---|---|---|
| `raw_logs` | ~200만 | GA4 이벤트 로그 |
| `event_items` | ~157만 | 구매 이벤트 아이템 상세 |

---

## 프로젝트 구조

```
K-PatternHunters/
├── docker-compose.yml
├── .env.example
├── frontend/                    # Vue 3 대시보드
│   └── src/views/Dashboard.vue
├── backend/
│   ├── main.py                  # FastAPI 앱 진입점
│   ├── requirements.txt
│   └── app/
│       ├── agents/              # LangGraph 에이전트
│       │   ├── context_agent.py
│       │   ├── insight_agent.py
│       │   ├── funnel_agent.py
│       │   ├── cohort_agent.py
│       │   ├── journey_agent.py
│       │   ├── performance_agent.py
│       │   ├── anomaly_agent.py
│       │   ├── prediction_agent.py
│       │   └── ppt_agent.py
│       ├── core/
│       │   ├── models.py        # Pydantic 데이터 모델
│       │   └── config.py        # 환경 변수 설정
│       ├── db/
│       │   └── mongo.py         # MongoDB 연결 관리
│       ├── graph/
│       │   └── pipeline.py      # LangGraph StateGraph 정의
│       ├── routers/
│       │   ├── analysis.py      # POST /analysis/run
│       │   └── status.py        # GET /analysis/status/{job_id}
│       ├── tools/
│       │   ├── rag_tool.py      # Qdrant RAG 검색
│       │   └── web_search_tool.py  # Tavily 웹검색
│       └── worker.py            # Celery 워커 정의
├── data/
│   ├── ingest/                  # BQ → MongoDB 적재 스크립트
│   └── ecom-data/               # NDJSON 원본 파일 (로컬 적재 시)
└── rag/
    ├── ingest_docs.py           # 문서 → Qdrant 적재
    └── pipeline/                # 임베딩 / 인덱싱 모듈
```

---

## 팀 (Roles & Responsibilities)

| 담당자 | 담당 범위 |
|---|---|
| 기동주 | Backend Develop |
| 김정우 | Frontend Develop |
| 서제임스 | Data Engineering |
| 신준용 | Backend Develop |

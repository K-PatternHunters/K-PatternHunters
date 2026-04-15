# K-PatternHunters — CLAUDE.md

## 프로젝트 개요

GA4 ecommerce 행동 데이터를 weekly로 분석하여 자동으로 PPT 보고서를 생성하는 멀티 에이전트 시스템.

- **Input:** Weekly raw GA4 event logs + domain category (사용자 입력)
- **Output:** 행동 패턴 분석 결과 + 자동 생성 PPT 보고서 (한국어)

---

## 팀 담당 분리

| 담당자 | 브랜치 | 담당 범위 |
|---|---|---|
| **epk4429** | `backend_dj` | context_agent, insight_agent, models, tests |
| **jy팀** | `backend_jy` | supervisor, schema_mapping, funnel, cohort, journey, performance, anomaly, prediction, _ga4_utils |
| **front팀** | `front` | Vue 3 프론트엔드 |

> **주의**: `supervisor.py`는 파이프라인에서 제거됨 — `analysis_dispatcher`가 해당 역할 대체.

---

## 전체 파이프라인

```
[START]
   │
context_agent           ← epk4429 구현. 도메인 분석 컨텍스트 생성 (LLM + RAG + 웹검색)
   │
analysis_dispatcher     ← pipeline.py 내 async 노드.
   │                       domain_context.recommended_sub_agents 기반 asyncio.gather 병렬 실행
   │                       (supervisor 제거 — dispatcher가 역할 통합)
   ├── funnel_agent
   ├── cohort_agent
   ├── journey_agent     ← jy팀 구현. MongoDB 직접 집계
   ├── performance_agent
   ├── anomaly_agent
   └── prediction_agent
          │
   insight_agent         ← epk4429 구현. 6개 분석 결과 종합 → 슬라이드별 InsightReport 생성 (LLM)
          │
   ppt_agent             ← jy팀 구현 완료. 8슬라이드 python-pptx
          │
        [END]
```

---

## 구현 현황

### epk4429 (backend_dj) 담당

| 파일 | 상태 | 비고 |
|---|---|---|
| `app/core/models.py` | ✅ 완료 | DomainContext, InsightReport, SlideContent, PipelineState, *Config 모델 전체 정의 |
| `app/core/config.py` | ✅ 완료 | pydantic-settings BaseSettings, .env 로드, lru_cache |
| `app/agents/context_agent.py` | ✅ 완료 | gpt-4o-mini, function_calling, RAG/웹검색 graceful fallback |
| `app/agents/insight_agent.py` | ✅ 완료 | gpt-4o, function_calling, 한국어 출력, 슬라이드 단위 구조화 |
| `app/agents/md_agents/context_agent.md` | ✅ 완료 | 설계 결정, 트러블슈팅 기록 |
| `app/agents/md_agents/insight_agent.md` | ✅ 완료 | 설계 결정, 트러블슈팅 기록 |
| `tests/conftest.py` | ✅ 완료 | GA4 BigQuery export 포맷 샘플 데이터 (20개 이벤트) |
| `tests/test_context_agent.py` | ✅ 완료 | 16개 테스트 |
| `tests/test_insight_agent.py` | ✅ 완료 | 12개 테스트 |
| `tests/test_pipeline.py` | ✅ 완료 | E2E 통합 테스트 10개 (전체 파이프라인) |
| `pytest.ini` | ✅ 완료 | asyncio_mode=auto |
| `.env.example` | ✅ 완료 | 환경변수 템플릿 |

### jy팀 (backend_jy) 담당

| 파일 | 상태 | 비고 |
|---|---|---|
| `app/agents/_ga4_utils.py` | ✅ 완료 | 공용 GA4 파싱 유틸 (전 agent import) |
| `app/agents/schema_mapping_agent.py` | ✅ 완료 | GA4 baseline + LLM (불일치 시만) |
| `app/agents/_agent_utils.py` | ✅ 완료 | retry loop 공통 유틸 (`validate_or_retry`, `error_patch`) |
| `app/agents/funnel_agent.py` | ✅ 완료 | 유저 단위 집계, breakdown + 비즈니스 검증 + retry |
| `app/agents/cohort_agent.py` | ✅ 완료 | first_purchase_week 코호트, retention/revenue + 비즈니스 검증 + retry |
| `app/agents/journey_agent.py` | ✅ 완료 | 세션 시퀀스, top-N 경로, transition matrix + 비즈니스 검증 + retry |
| `app/agents/performance_agent.py` | ✅ 완료 | 주간 KPI + daily/source/device/category + WoW + 비즈니스 검증 + retry |
| `app/agents/anomaly_agent.py` | ✅ 완료 | Z-score + LLM 한국어 해석 (검증 제외 — 내부 baseline 경고 처리로 충분) |
| `app/agents/prediction_agent.py` | ✅ 완료 | linear least-squares + LLM 한국어 코멘트 + 비즈니스 검증 + retry |
| `app/agents/ppt_agent.py` | ✅ 완료 | 8슬라이드 고정 구조, python-pptx, 도메인 가변 Slide 6 |

### 공통 인프라 (main 브랜치 통합)

| 파일 | 상태 | 비고 |
|---|---|---|
| `app/graph/pipeline.py` | ✅ 완료 | LangGraph StateGraph. context_agent → analysis_dispatcher(병렬) → insight_agent → ppt_agent |
| `app/db/mongo.py` | ✅ 완료 | motor AsyncIOMotorClient. connect/disconnect/get_collection. Collections: events, analysis_results, job_status |
| `app/tools/web_search_tool.py` | ✅ 완료 | Tavily 웹검색. `web_search(query, max_results)` async 함수 |
| `app/tools/rag_tool.py` | ✅ 완료 | Qdrant RAG. `rag_search(query, domain, top_k)`. `rag/pipeline/` 하위 embedder/indexer 사용 |
| `rag/pipeline/embedder.py` | ✅ 완료 | sentence-transformers 기반 임베딩 (로컬, API 키 불필요) |
| `rag/pipeline/indexer.py` | ✅ 완료 | Qdrant 컬렉션 인덱싱 |
| `rag/pipeline/loader.py` | ✅ 완료 | 문서 로드 및 청킹 |
| `rag/ingest_docs.py` | ✅ 완료 | 문서 → Qdrant 적재 스크립트 |

### 미완료

| 파일 | 상태 | 비고 |
|---|---|---|
| `app/routers/analysis.py` | ⚠️ 미연결 | Celery task로 파이프라인 실행 연결 필요 |

---

## 핵심 데이터 모델 (`app/core/models.py`)

### PipelineState (LangGraph state dict)

```python
class PipelineState(TypedDict, total=False):
    # 입력
    job_id: str
    period: str                  # "weekly"
    domain_description: str
    raw_logs: list[dict]
    log_ids: list[str]
    week_start: str              # "YYYYMMDD"
    week_end: str                # "YYYYMMDD"

    # context_agent 출력
    domain_context: dict         # DomainContext.model_dump()

    # schema_mapping_agent 출력
    field_mapping: dict

    # 분석 에이전트 출력
    funnel_metrics: dict
    cohort_metrics: dict
    journey_metrics: dict
    performance_metrics: dict
    anomaly_metrics: dict
    prediction_metrics: dict

    # insight_agent 출력
    insight_report: dict         # InsightReport.model_dump()

    # ppt_agent 출력
    ppt_url: str
```

### DomainContext (context_agent 출력)

```
DomainContext
├── domain, domain_summary
├── analysis_priorities, recommended_sub_agents
├── key_metrics, interpretation_guidelines, industry_benchmarks
├── funnel_config       → FunnelConfig(steps)
├── cohort_config       → CohortConfig(cohort_basis, user_key, metrics)
├── journey_config      → JourneyConfig(top_n, max_depth, split_by_outcome)
├── performance_config  → PerformanceConfig(kpis, breakdowns)
├── anomaly_config      → AnomalyConfig(target_metrics, method, threshold)
├── prediction_config   → PredictionConfig(targets, method, lookback_weeks)
├── log_schema_hints
├── rag_references
└── search_references
```

각 분석 에이전트는 `state["domain_context"]["funnel_config"]["steps"]` 형태로 접근.

### InsightReport (insight_agent 출력)

```
InsightReport
├── domain, analysis_period, overall_sentiment
├── executive_summary, top_findings, recommendations
├── performance_slide   → SlideContent | None
├── funnel_slide        → SlideContent | None
├── cohort_slide        → SlideContent | None
├── journey_slide       → SlideContent | None
├── anomaly_slide       → SlideContent | None
├── prediction_slide    → SlideContent | None
├── cross_analysis_findings
└── slide_order         (ppt_agent용 슬라이드 순서)

SlideContent 필드: slide_type, title, headline, bullets,
                   metrics, chart_type, chart_data_key, speaker_notes
```

---

## 데이터 소스

- **Origin:** GA4 BigQuery `ga4_obfuscated_sample_ecommerce` 샘플 데이터셋
- **Storage:** MongoDB `ga4_ecommerce` DB, `events` collection (config: `MONGO_DB`, `MONGO_COLLECTION`)
- **Document 구조:** GA4 BigQuery export nested 원본 그대로

### GA4 필드 구조 (중요 — flat string이 아닌 nested object)

```python
{
    "event_date": "20240318",          # "YYYYMMDD"
    "event_timestamp": 1710720000000000,
    "event_name": "purchase",
    "user_pseudo_id": "user_001",
    "event_params": [{"key": "ga_session_id", "value": {"int_value": 1001}}],
    "traffic_source": {"source": "google", "medium": "cpc", "name": "spring_sale"},  # nested!
    "device": {"category": "mobile"},   # nested!
    "geo": {"country": "KR", "city": "Seoul"},
    "ecommerce": {"transaction_id": "T001", "purchase_revenue": 89000},  # purchase_revenue!
    "items": [{"item_id": "SKU-A", "item_name": "...", "item_category": "...", "price": 89000, "quantity": 1}]
}
```

> ⚠️ `traffic_source`는 string이 아닌 `{"source": "...", "medium": "..."}` dict.
> `ecommerce` revenue 키는 `purchase_revenue` (value, revenue 아님).
> `_ga4_utils.py`의 파서가 이 포맷을 기준으로 작성됨.

---

## 기술 스택

| 역할 | 기술 |
|---|---|
| Web framework | FastAPI |
| LLM | OpenAI GPT-4o / GPT-4o-mini (`langchain-openai`) |
| Agent orchestration | LangGraph (StateGraph) |
| DB (async) | MongoDB — `motor` |
| Vector DB | Qdrant |
| Task queue | Celery + Redis |
| PPT 생성 | python-pptx |
| 웹검색 | Tavily (`tavily-python`) |
| RAG 임베딩 | sentence-transformers (로컬) |
| 설정 관리 | pydantic-settings (.env 로드) |
| 테스트 | pytest + pytest-asyncio |

---

## 환경 설정

```bash
# 1. 가상환경 활성화
cd backend
source .venv/bin/activate

# 2. .env 파일 생성
cp .env.example .env
# .env에 OPENAI_API_KEY=sk-... 입력

# 3. 의존성 설치
pip install -r requirements.txt
```

### .env 필수 변수

```
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...          # 웹검색 (선택 — 없으면 graceful fallback)

# MongoDB (개별 설정 방식)
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB=ga4_ecommerce
MONGO_COLLECTION=events
# 또는 URI 방식 (MONGODB_URI 설정 시 개별 설정보다 우선)
MONGODB_URI=

QDRANT_URL=http://localhost:6333
QDRANT_HOST=localhost            # rag_tool용
QDRANT_PORT=6333
REDIS_URL=redis://localhost:6379/0

# BigQuery → MongoDB 적재 (ingest 시에만 필요)
BQ_PROJECT_ID=
BQ_DATASET=bigquery-public-data.ga4_obfuscated_sample_ecommerce
BQ_DATE_START=20210115
BQ_DATE_END=20210131
SA_KEY_PATH=                     # GCP 서비스 계정 키 파일 경로
```

---

## 테스트 실행

```bash
cd backend

# context_agent만
python -m pytest tests/test_context_agent.py -v -s

# insight_agent만
python -m pytest tests/test_insight_agent.py -v -s

# 전체 파이프라인 E2E (약 2분 소요, LLM 호출 포함)
python -m pytest tests/test_pipeline.py -v -s

# 전체
python -m pytest tests/ -v
```

### 테스트 통과 현황 (마지막 확인: 2026-04-14)

- `test_context_agent.py` — 16개 중 15개 PASS (1개 ValueError 검증용)
- `test_insight_agent.py` — 12개 PASS
- `test_pipeline.py` — **10/10 PASS** (E2E 전체 파이프라인)

---

## 핵심 설계 결정 및 트러블슈팅

### 1. DomainContext 포맷: Pydantic → dict

LangGraph state는 TypedDict(dict) 기반이므로 `.model_dump()`로 변환해 저장.
하위 에이전트는 파싱 없이 `state["domain_context"]["funnel_config"]["steps"]`로 직접 접근.

### 2. InsightReport: 슬라이드 단위 구조화

ppt_agent가 LLM 재호출 없이 바로 렌더링할 수 있도록 `SlideContent` 단위로 출력.
`chart_type`(funnel_chart/heatmap/sankey 등), `chart_data_key`(원본 metrics 참조 키) 포함.

### 3. method="function_calling" 필수

`dict[str, Any]` 타입 필드가 포함된 Pydantic 모델을 OpenAI structured output에 사용 시
strict mode에서 `additionalProperties: false` 오류 발생.
→ `.with_structured_output(Model, method="function_calling")` 으로 해결.

### 4. GA4 샘플 데이터 포맷

`_ga4_utils.py`는 GA4 BigQuery export 원본 포맷(nested objects)을 기대함.
테스트 fixture에서 `traffic_source`를 flat string으로 쓰면 AttributeError 발생.
→ `conftest.py`에서 `{"source": "google", "medium": "cpc"}` nested 포맷으로 수정.

### 5. insight_agent 언어 설정

시스템 프롬프트 첫 줄에 한국어 출력 명시.
`chart_type`, `chart_data_key`, `slide_type` 등 코드성 식별자는 영어 유지.

---

## 에이전트별 상세 노트

각 에이전트의 설계 결정과 트러블슈팅은 아래 위치에 기록:

```
backend/app/agents/md_agents/
├── context_agent.md
└── insight_agent.md
```

---

## 프로젝트 파일 구조

```
K-PatternHunters/
├── CLAUDE.md                        ← 이 파일
├── docker-compose.yml
├── docs/
│   ├── architecture.md
│   └── agents/                      ← jy팀 에이전트 스펙 문서
│       ├── supervisor.md
│       ├── schema_mapping.md
│       ├── funnel.md  cohort.md  journey.md
│       ├── performance.md  anomaly.md  prediction.md
│       └── ...
├── frontend/                        ← Vue 3 (front팀)
└── backend/
    ├── .env                         ← OPENAI_API_KEY 등 (git 제외)
    ├── .env.example
    ├── main.py                      ← FastAPI 앱 엔트리포인트
    ├── requirements.txt
    ├── pytest.ini
    ├── .venv/
    ├── tests/
    │   ├── conftest.py              ← GA4 샘플 데이터, 공용 fixture
    │   ├── test_context_agent.py
    │   ├── test_insight_agent.py
    │   └── test_pipeline.py        ← E2E 통합 테스트
    └── app/
        ├── agents/
        │   ├── md_agents/           ← 에이전트별 개발 노트
        │   │   ├── context_agent.md
        │   │   └── insight_agent.md
        │   ├── _ga4_utils.py        ← GA4 파싱 유틸 (모든 agent import)
        │   ├── _agent_utils.py      ← retry loop 공통 유틸 (validate_or_retry, error_patch)
        │   ├── context_agent.py     ← epk4429
        │   ├── insight_agent.py     ← epk4429
        │   ├── schema_mapping_agent.py ← jy팀
        │   ├── funnel_agent.py      ← jy팀
        │   ├── cohort_agent.py      ← jy팀
        │   ├── journey_agent.py     ← jy팀
        │   ├── performance_agent.py ← jy팀
        │   ├── anomaly_agent.py     ← jy팀
        │   ├── prediction_agent.py  ← jy팀
        │   └── ppt_agent.py         ← jy팀 구현 완료 (8슬라이드)
        ├── core/
        │   ├── config.py            ← pydantic-settings, lru_cache, mongodb_uri property
        │   └── models.py            ← 전체 Pydantic 모델 정의 (564줄)
        ├── db/
        │   ├── mongo.py             ← ✅ motor 구현 완료 (connect/disconnect/get_collection)
        │   └── qdrant.py
        ├── graph/
        │   └── pipeline.py          ← ✅ LangGraph StateGraph 구현 완료
        ├── routers/
        │   ├── analysis.py          ← POST /analysis/run (Celery 연결 미완료)
        │   └── status.py            ← GET /analysis/status/{job_id}
        └── tools/
            ├── rag_tool.py          ← ✅ Qdrant RAG 구현 완료
            └── web_search_tool.py   ← ✅ Tavily 웹검색 구현 완료
    └── rag/
        ├── ingest_docs.py           ← 문서 → Qdrant 적재 스크립트
        ├── documents/               ← 적재할 원본 문서
        └── pipeline/
            ├── embedder.py          ← sentence-transformers 임베딩
            ├── indexer.py           ← Qdrant 컬렉션 인덱싱
            └── loader.py            ← 문서 로드 및 청킹
```

---

## Agent Output Validation 체계

### 두 단계 검증

각 분석 agent(funnel/cohort/journey/performance/prediction)는 두 단계 검증을 거침:

1. **비즈니스 로직 검증** (retry 대상) — 결과가 의미 있는지 판단
2. **스키마 검증** (Pydantic, 로그만) — 결과 구조/타입이 맞는지 확인

### Retry 동작 (`_agent_utils.py`)

```
attempt 1 → _run(state) → errors? → WARNING 로그 → retry
attempt 2 → _run(state) → errors? → WARNING 로그 → retry
attempt 3 → _run(state) → errors? → ERROR 로그 "exhausted 3 retries"
             → 마지막 결과 반환 (파이프라인 중단 없음)
```

실패 시 `state["validation_errors"]` 에 에러 내용 기록:
```python
{"funnel_agent": ["첫 단계 user_count == 0 — 데이터 범위 또는 event_name 불일치 확인 필요"]}
```

### Agent별 비즈니스 검증 조건

| agent | 검증 조건 |
|---|---|
| `funnel_agent` | 첫 단계 `user_count == 0` |
| `cohort_agent` | `cohorts` 리스트 비어있음 |
| `journey_agent` | `total_sessions == 0` |
| `performance_agent` | `session_count == 0` |
| `prediction_agent` | 전체 predictions가 모두 `skipped` |
| `anomaly_agent` | 검증 제외 (내부 baseline 부족 경고로 충분) |

### Sub-agent Output Pydantic 모델 (`app/core/models.py`)

`FunnelMetrics`, `CohortMetrics`, `JourneyMetrics`, `PerformanceMetrics`, `AnomalyMetrics`, `PredictionMetrics` — 각 agent 출력 dict의 스키마 정의.

---

## PPT Agent 슬라이드 구조

8슬라이드 고정 구조. `PPT_OUTPUT_DIR` 환경변수로 출력 경로 지정 (기본 `/tmp/ppt_reports/`).

| 슬라이드 | 제목 | 시각화 |
|---|---|---|
| Slide 1 | Executive Summary | KPI 카드 3개 (매출/전환율/세션) + WoW 증감 |
| Slide 2 | 주요 지표 현황 | KPI 테이블 + 일별 breakdown |
| Slide 3 | 이상 감지 결과 | Z-score 강조 테이블 (|z|≥3 빨간색) |
| Slide 4 | 사용자 흐름 분석 | 퍼널 테이블 + 전환 경로 Top 5 |
| Slide 5 | 고객 세그먼트 분석 | 디바이스/소스별 비교 + 코호트 요약 |
| Slide 6 | **도메인 가변** | e-commerce: 카테고리별 구매 테이블 |
| Slide 7 | 예측 및 시사점 | 예측값 + 신뢰구간 + LLM 코멘트 |
| Slide 8 | 권장 액션 | P1/P2/P3 우선순위 + 교차 분석 인사이트 |

**도메인 전환 시 Slide 6만 수정** (`_build_slide6_domain` 함수 내 분기 추가).

---

## 완료된 작업 (2026-04-15)

### 인프라
- `app/worker.py` 신규 — Celery 앱 + `run_pipeline_task` 정의
- `app/routers/analysis.py` — `BackgroundTasks` → `run_pipeline_task.delay()` 교체
- `docker-compose.yml` — `worker` 서비스 추가 (backend 이미지 재사용, celery 명령으로 실행)

### 데이터 적재
- `data/ingest/transform.py` — `d.pop("items", None)` 제거 → `items` 배열이 `raw_logs`에 embed됨 (**하지만 실제로는 embed 안됨 — 아래 참고**)
- MongoDB: `customer_behavior` DB, `raw_logs` 컬렉션 (약 200만 건, `20201215~20210131`), `event_items` 컬렉션 (1,574,780건)
- ⚠️ `items`는 `raw_logs`에 embed되지 않고 별도 `event_items` 컬렉션에 저장됨 (transform.py 수정에도 불구하고)

### Trouble Shooting(버그 수정) (2026-04-15 세션)

#### 1. MongoDB 잘못된 DB 접근 — session_count=0 근본 원인 해결
- **증상**: performance/funnel/journey agent가 모두 ~35ms에 0 반환. cohort/anomaly는 정상.
- **원인**: `get_collection()`이 `MONGO_DB` env var(`ga4_ecommerce` 기본값)을 사용해 잘못된 DB 접근.
  `MONGODB_URI`에 DB 이름(`customer_behavior`)이 포함돼 있었지만 무시됨.
- **수정**: `app/db/mongo.py` — `MONGODB_URI` 설정 시 `_client.get_default_database()` 사용:
  ```python
  def get_collection(name: str):
      if settings.MONGODB_URI:
          try:
              return _client.get_default_database()[name]
          except Exception:
              pass
      return _client[settings.MONGO_DB][name]
  ```

#### 2. by_category 빈 배열 — event_items 컬렉션 분리
- **증상**: `$unwind: "$items"` 결과 빈 배열. Playground에서도 재현됨.
- **원인**: `items` 필드가 `raw_logs`에 없음. 별도 `event_items` 컬렉션에 1,574,780건 존재.
- **수정**: `performance_agent.py` — `$facet`에서 `by_category` 서브파이프라인 제거.
  `_aggregate_by_category()` 함수 신규 추가 — `event_items` 컬렉션 직접 조회:
  ```python
  async def _aggregate_by_category(items_col, start: str, end: str) -> list[dict]:
      pipeline = [
          {"$match": {"event_date": {"$gte": start, "$lte": end},
                      "event_name": {"$in": ["view_item", "add_to_cart", "purchase"]}}},
          {"$group": {"_id": {"$ifNull": ["$item_category", "unknown"]},
                      "view_count": ..., "add_to_cart_count": ...,
                      "purchase_count": ..., "revenue": ...}},
          {"$sort": {"revenue": -1}},
      ]
  ```
  `_run()` 내 `items_col = get_collection("event_items")` 추가.

#### 3. PPT 출력 품질 개선
- `ppt_agent.py`:
  - 통화 기호 `₩` → `$`
  - ARPU → ARPPU (`total_revenue / transaction_count`)
  - 예측 지표명 한국어 매핑 (`_PREDICTION_TARGET_KO` dict): `next_week_revenue` → `다음 주 매출` 등
  - LLM 코멘트 글자 수 제한 `[:60]` → `[:120]`
- `prediction_agent.py` — 데이터 부족 경고 한국어화:
  `"Only N weeks of data..."` → `"데이터 N주치만 확보됨 (요청: M주) — 예측 신뢰도 낮음"`
- `insight_agent.py` — `_SYSTEM_PROMPT` 강화:
  - bullet 포맷 강제: `"[지표명] [수치] — [비교] → [비즈니스 의미]"`
  - 수치 없는 bullet 금지 명시
  - recommendation 포맷 강제: `"[구체적 액션] — 근거: [분석명]에서 [수치/패턴] 발견."`

#### 4. 프론트엔드 기준일 기본값 설정
- `frontend/src/views/Dashboard.vue`:
  - `analysisDate = ref('')` → `ref('2020-12-22')` (데이터 존재 날짜로 기본값)
  - `<input type="date">` 에 `min="2020-12-15" max="2021-01-31"` 속성 추가

### 버그 수정 (2026-04-15 세션 2차)

#### 5. 프론트엔드 날짜 범위 8일 표시 버그
- **증상**: 분석 기준일 선택 후 "일주일" 버튼 클릭 시 7일이 아닌 8일 범위로 표시.
- **원인**: `start.setDate(start.getDate() - periodDays[period.value])` — end date를 포함한 inclusive 범위에서 7을 빼야 하므로 6을 빼야 함.
- **수정**: `frontend/src/views/Dashboard.vue` — `periodDays - 1` 로 변경. 실제 API 전송 범위(week_start~week_end)도 동일하게 7일 고정 확인.

#### 6. Anomaly baseline 부족 — 초기 주차 Z-score 신뢰도 낮음
- **증상**: Dec 22일 주차 분석 시 베이스라인 7일치만 사용. Z-score 기댓값 불안정.
- **원인**: 데이터가 12월 15일부터 시작 → 4주 lookback(28일) 확보 불가.
- **수정**: `anomaly_agent.py` — `_LOOKBACK_WEEKS_MAX = 26` 추가. baseline < 7일이면 26주로 자동 확장. `summary`에 `baseline_days_available`, `baseline_start` 추가. PPT Slide 3에 14일 미만 시 경고 배너 표시.

#### 7. performance_agent — by_geo / 신규·재방문 사용자 누락
- **증상**: Slide 5에 국가별 / 신규 vs 재방문 테이블 없음.
- **원인**: `performance_agent.py`에 해당 집계 파이프라인 미구현.
- **수정**: `_aggregate_week()` `$facet`에 `by_geo`(top 8 국가), `new_users`(`first_visit` 이벤트) 서브파이프라인 추가. `new_vs_returning` dict 계산 후 반환.

#### 8. 카테고리 구매율 이상값 (Accessories 2400%, New 214%)
- **증상**: view_count=2~41인 카테고리에서 구매율이 수백~수천%로 표시.
- **원인**: `view_count > 0`이면 `purchase_count / view_count` 계산 → 소량 조회 시 분모가 너무 작음.
- **수정**: `performance_agent.py` — `view_count >= 10` 미만이면 `purchase_rate = None` (PPT에서 "N/A" 표시).

#### 9. Cohort W0 retention_rate = 0% 버그
- **증상**: 코호트 히트맵 W0 컬럼이 100%가 아닌 0~수% 로 표시.
- **원인 1**: `_ga4_utils.py` `week_offset()`이 `%Y-W%W-%w` (Python 비표준) 사용 → 2020-W53처럼 ISO와 비표준이 다른 연말 주차에서 파싱 오류.
- **원인 2**: W0는 코호트 기준 주 자체이므로 구매 여부와 무관하게 retention=1.0 이어야 하는데 실제 구매 이벤트로 계산함.
- **수정**: `_ga4_utils.py` → `%G-W%V-%u` (ISO 8601) 로 변경. `cohort_agent.py` → `week_offset == 0`이면 `retention_rate = 1.0`, `retained_users = cohort_size` 강제.

#### 10. insight_agent WoW 방향 오류 (`_fmt_k` 미정의)
- **증상**: WoW 방향 요약 블록에서 `NameError: name '_fmt_k' is not defined` 발생.
- **원인**: WoW 수치 포맷 함수 `_fmt_k`를 호출하는 코드가 추가됐으나 해당 함수가 insight_agent.py에 없음.
- **수정**: `_fmt_k(...)` → `f"${kpis.get('total_revenue', 0):,.0f}"` 인라인 포맷으로 교체.

#### 11. PPT Slide 4 이탈/전환 경로 텍스트 오버플로
- **증상**: `session_start → user_engagement → ...` 같은 긴 이벤트명 조합이 셀을 벗어남.
- **원인**: journey_agent가 GA4 원시 이벤트명(snake_case 풀네임)을 그대로 반환. 테이블 컬럼 폭 대비 너무 긺.
- **수정**: `ppt_agent.py` — `_EVENT_SHORT` (영문 약어), `_EVENT_KO` (한국어) 딕셔너리 추가. 이탈/전환 경로는 약어, 퍼널 테이블·바 차트 축은 한국어 사용.

#### 12. PPT Slide 5 섹션 레이블·테이블 겹침
- **증상**: "신규 vs 재방문 사용자" 레이블이 디바이스 테이블에, "코호트 리텐션" 레이블이 NVR 테이블에 가려짐.
- **원인**: 각 섹션의 top 좌표가 이전 테이블 끝보다 위로 설정됨 (NVR_TOP=3.35" < 디바이스 테이블 끝 3.45", 코호트 레이블=4.67" < NVR 테이블 끝 4.95").
- **수정**: `ppt_agent.py` `_build_slide5_segment()` — 위→아래 순서로 S1/S2/S3 위치를 명시적으로 계산 (`S2_LABEL = S1_BOT + GAP`, `S3_LABEL = S2_BOT + GAP`). 겹침 구조적으로 불가능하게 재설계.

#### 13. PPT Slide 7 LLM 코멘트 레이아웃 불량
- **증상**: "코멘트" 컬럼이 좁은 셀에 긴 텍스트를 넣어 줄바꿈 과다, 가독성 낮음.
- **원인**: 코멘트를 테이블 컬럼 내에 포함시킨 설계.
- **수정**: `ppt_agent.py` — 테이블에서 "코멘트" 컬럼 제거 (4컬럼으로 축소). 코멘트는 테이블 아래 "LLM 시사점" 섹션에 bullet list로 분리 렌더링.

### 현재 파이프라인 상태 (2026-04-15 최종)
- **모든 에이전트 정상 동작 확인** — Dec 15-22 / Jan 16-22 두 기간 PPT 생성 완료
- Apparel 카테고리 최다 구매 등 `event_items` 데이터 정상 반영
- 코호트 W0 = 100%, 국가별/신규재방문 테이블 정상 표시
- `docker compose restart worker` 필수 — Python 파일 수정 후 항상 재시작

---

## MongoDB 컬렉션 구조 (실제)

| 컬렉션 | 건수 | 내용 |
|---|---|---|
| `raw_logs` | ~200만 | GA4 이벤트 (items 필드 없음) |
| `event_items` | 1,574,780 | 구매 이벤트의 items 배열 (분리 저장) |

> `event_items` 도큐먼트 구조: `event_date`, `event_name`, `user_pseudo_id`, `item_id`, `item_name`, `item_category`, `price`, `quantity`, `revenue`

---

## 다음 작업 우선순위

1. **RAG 문서 적재** — `rag/ingest_docs.py` 실행해 Qdrant에 문서 적재 (context_agent RAG 기능 활성화)
2. **funnel/journey agent by_category 여부 확인** — performance_agent만 수정됨, 다른 agent도 items 필요 시 `event_items` 컬렉션 사용해야 함
3. (선택) `event_items` 컬렉션 drop — 아무도 사용 안 한다면 정리

---

## 협업 구조 문제 분석 — 개발명세서 부재로 인한 버그 분류

3인 협업 시 구두/줄글로만 인터페이스를 합의하고 각자 개발 후 main merge하는 방식으로 진행됨.
아래 버그들은 **개발명세서(인터페이스 명세, 데이터 스키마, 컬렉션 명세)가 있었다면 사전에 방지 가능**했던 것들임.

### 개발명세서 부재가 직접 원인인 버그

| # | 버그 | 근본 원인 |
|---|---|---|
| **1** | MongoDB DB명 불일치 (`ga4_ecommerce` vs `customer_behavior`) | DB명/컬렉션명을 명세 없이 구두로 협의. env 기본값과 실제 URI 내 DB명이 따로 놀았음 |
| **2** | `items` 필드 위치 — `raw_logs` embed vs `event_items` 별도 컬렉션 | 데이터 적재 담당(데이터팀)과 분석 에이전트 담당(백엔드팀)이 컬렉션 구조를 서로 다르게 이해. 명세 없이 진행 |
| **9** | `week_offset()` ISO 주차 파싱 오류 (`%W` vs `%V`) | `_ga4_utils.py`를 공용 유틸로 작성했으나 ISO 8601 vs Python 기본 주차 포맷 차이를 명세에 정의 안 함 |
| **7** | `by_geo` / 신규재방문 누락 | performance_agent 출력 스키마를 PPT 담당자와 합의 없이 작성. ppt_agent가 없는 키를 참조 |
| **8** | 카테고리 구매율 2400% 이상값 | `purchase_rate` 계산 조건(최소 view_count 임계값)을 명세에 정의 안 함. 담당자 간 "구매율" 정의 불일치 |
| **11** | Slide 4 경로 텍스트 오버플로 | journey_agent 출력 포맷(이벤트명 raw vs 약어)을 ppt_agent 담당자와 사전 합의 안 함 |

### 개발명세서와 무관한 버그 (구현 실수)

| # | 버그 | 성격 |
|---|---|---|
| **5** | 프론트 날짜 범위 8일 표시 | 단순 off-by-one 계산 오류 |
| **6** | Anomaly baseline 부족 | 데이터 기간 제약 (12/15 시작)을 사전에 예측 못한 것 — 설계 이슈지만 명세보다는 도메인 이해 문제 |
| **10** | `_fmt_k` 미정의 NameError | 단순 코딩 실수 |
| **12** | Slide 5 레이블 겹침 | PPT 레이아웃 수치 계산 실수 |
| **13** | Slide 7 코멘트 레이아웃 | UX 설계 판단 문제 |

### 결론

발생한 버그 13개 중 **6개(#1, #2, #7, #8, #9, #11)가 개발명세서 부재로 인한 인터페이스 불일치**에서 비롯됨.

공통 패턴:
- **데이터 스키마 명세 없음** — DB명, 컬렉션 구조, 필드 위치를 구두로만 협의 (#1, #2)
- **에이전트 출력 포맷 명세 없음** — 한 에이전트의 출력 dict 구조를 다른 에이전트 담당자가 다르게 가정 (#7, #11)
- **지표 계산 정의 없음** — "구매율", "retention rate" 등의 계산 조건을 명세 없이 각자 구현 (#8, #9)

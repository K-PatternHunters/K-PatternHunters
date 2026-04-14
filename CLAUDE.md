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

> **주의**: `ppt_agent.py`는 아직 미구현 상태 (placeholder).

---

## 전체 파이프라인

```
[START]
   │
context_agent        ← epk4429 구현. 도메인 분석 컨텍스트 생성 (LLM + RAG + 웹검색)
   │
supervisor           ← jy팀 구현. domain_context.recommended_sub_agents 기반 라우팅 결정
   │
schema_mapping_agent ← jy팀 구현. GA4 필드 → 정규화 필드명 매핑
   │
   ├── funnel_agent
   ├── cohort_agent
   ├── journey_agent       ← jy팀 구현. 병렬 실행 (LangGraph 설계)
   ├── performance_agent
   ├── anomaly_agent
   └── prediction_agent
          │
   insight_agent      ← epk4429 구현. 6개 분석 결과 종합 → 슬라이드별 InsightReport 생성 (LLM)
          │
   ppt_agent          ← 미구현 (placeholder)
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
| `app/agents/supervisor.py` | ✅ 완료 | deterministic, LLM 없음 |
| `app/agents/schema_mapping_agent.py` | ✅ 완료 | GA4 baseline + LLM (불일치 시만) |
| `app/agents/funnel_agent.py` | ✅ 완료 | 유저 단위 집계, breakdown |
| `app/agents/cohort_agent.py` | ✅ 완료 | first_purchase_week 코호트, retention/revenue |
| `app/agents/journey_agent.py` | ✅ 완료 | 세션 시퀀스, top-N 경로, transition matrix |
| `app/agents/performance_agent.py` | ✅ 완료 | 주간 KPI + daily/source/device/category + WoW |
| `app/agents/anomaly_agent.py` | ✅ 완료 | Z-score + LLM 한국어 해석 |
| `app/agents/prediction_agent.py` | ✅ 완료 | linear least-squares + LLM 한국어 코멘트 |

### 미완료

| 파일 | 상태 | 비고 |
|---|---|---|
| `app/agents/ppt_agent.py` | ❌ placeholder | python-pptx 구현 필요 |
| `app/graph/pipeline.py` | ❌ placeholder | LangGraph StateGraph 정의 필요 |
| `app/db/mongo.py` | ❌ placeholder | motor AsyncIOMotorClient 연결 필요 |
| `app/tools/rag_tool.py` | ❌ placeholder | Qdrant RAG 구현 필요 (현재 빈 리스트 반환) |
| `app/tools/web_search_tool.py` | ❌ placeholder | Tavily 웹검색 구현 필요 (현재 빈 리스트 반환) |

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

    # supervisor 출력
    sub_agents_plan: list[str]

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
- **Storage:** MongoDB `customer_behavior` DB, `raw_logs` collection
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
MONGODB_URI=mongodb://localhost:27017/customer_behavior
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379/0
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
        │   ├── context_agent.py     ← epk4429
        │   ├── insight_agent.py     ← epk4429
        │   ├── supervisor.py        ← jy팀
        │   ├── schema_mapping_agent.py ← jy팀
        │   ├── funnel_agent.py      ← jy팀
        │   ├── cohort_agent.py      ← jy팀
        │   ├── journey_agent.py     ← jy팀
        │   ├── performance_agent.py ← jy팀
        │   ├── anomaly_agent.py     ← jy팀
        │   ├── prediction_agent.py  ← jy팀
        │   └── ppt_agent.py         ← 미구현
        ├── core/
        │   ├── config.py            ← pydantic-settings, lru_cache
        │   └── models.py            ← 전체 Pydantic 모델 정의
        ├── db/
        │   ├── mongo.py             ← 미구현
        │   └── qdrant.py
        ├── graph/
        │   └── pipeline.py          ← 미구현 (LangGraph StateGraph)
        ├── routers/
        │   ├── analysis.py          ← POST /analysis/run
        │   └── status.py            ← GET /analysis/status/{job_id}
        └── tools/
            ├── rag_tool.py          ← 미구현 (Qdrant RAG)
            └── web_search_tool.py   ← 미구현 (Tavily)
```

---

## 다음 작업 우선순위

1. **ppt_agent** — InsightReport.slide_order 순서대로 python-pptx 슬라이드 생성
2. **pipeline.py** — LangGraph StateGraph 정의 (schema_mapping 후 6개 병렬 팬아웃)
3. **rag_tool / web_search_tool** — context_agent에서 실제 RAG/웹검색 활성화
4. **db/mongo.py** — motor 연결 구현, raw_logs MongoDB에서 직접 로드
5. **routers/analysis.py** — Celery task로 파이프라인 실행 연결

# K-PatternHunters — CLAUDE.md

## 프로젝트 개요

GA4 ecommerce 행동 데이터를 weekly로 분석하여 자동으로 PPT 보고서를 생성하는 멀티 에이전트 시스템.

- **Input:** Weekly raw GA4 event logs (MongoDB) + domain category
- **Output:** 행동 패턴 분석 결과 + 자동 생성 PPT 보고서

---

## 팀 담당 분리

**이 레포에서 내가 담당하는 범위:**
- Supervisor Agent
- Schema Mapping Agent
- Funnel / Cohort / Journey / Performance / Anomaly / Prediction Agent

**타팀 담당 (이미 인터페이스만 정의됨, 건드리지 말 것):**
- Context Agent — 도메인 RAG + web search → `AnalysisContext` 생성
- Insight Agent — 6개 분석 결과 종합 해석
- PPT Agent — 저번 주 보고서 비교 + PowerPoint 생성

---

## 데이터 소스

- **Origin:** GA4 BigQuery `ga4_obfuscated_sample_ecommerce` 샘플 데이터셋
- **Storage:** MongoDB `customer_behavior` DB, `raw_logs` collection
- **Document 구조:** GA4 BigQuery export nested 원본 그대로 (`event_params[]`, `items[]`, `ecommerce{}` 등)
- **Weekly 구분:** `event_date` 필드 range (format: `YYYYMMDD`, e.g. `20210101`~`20210107`)
- **볼륨:** 수만~수십만 documents/week 가정 → **모든 agent는 MongoDB aggregation pipeline 기반으로 처리, raw document 전체 메모리 로드 금지**

---

## 아키텍처

### Agent Pipeline

```
[START]
   │
context_agent      ← 타팀. AnalysisContext 생성 후 supervisor로 전달
   │
supervisor         ← schema_mapping 완료 후 분석 6개 병렬 팬아웃
   │
schema_mapping_agent
   │
   ├── funnel_agent
   ├── cohort_agent
   ├── journey_agent       ← 병렬 실행
   ├── performance_agent
   ├── anomaly_agent
   └── prediction_agent
          │
   insight_agent   ← 타팀
          │
   ppt_agent       ← 타팀
          │
        [END]
```

### LangGraph State

중간 결과는 MongoDB에 저장하지 않고 LangGraph state로만 전달. 최종 결과만 DB 저장.

```python
class PipelineState(TypedDict):
    week_start: str
    week_end: str
    domain: str
    context: AnalysisContext      # Context Agent output
    field_mapping: dict           # Schema Mapping Agent output
    funnel_result: dict
    cohort_result: dict
    journey_result: dict
    performance_result: dict
    anomaly_result: dict
    prediction_result: dict
    insight: dict                 # 타팀
    ppt_url: str                  # 타팀
```

### AnalysisContext (Context Agent → Supervisor 전달 스펙)

```python
{
    "domain": "ecommerce",
    "funnel": {
        "steps": ["session_start", "view_item", "add_to_cart", "begin_checkout", "purchase"],
        "key_metric": "conversion_rate"
    },
    "cohort": {
        "definition": "first_purchase_week",
        "metrics": ["retention_rate", "revenue_per_user"]
    },
    "journey": {
        "top_n_paths": 10,
        "max_depth": 5,
        "entry_events": ["session_start"],
        "exit_events": ["purchase", "session_end"]
    },
    "performance": {
        "kpis": ["total_revenue", "transaction_count", "arpu", "session_count", "conversion_rate", "bounce_rate"],
        "breakdowns": ["traffic_source", "device_category"]
    },
    "anomaly": {
        "target_metrics": ["daily_revenue", "daily_session_count", "daily_conversion_rate"],
        "method": "zscore",
        "threshold": 2.0
    },
    "prediction": {
        "targets": ["next_week_revenue", "next_week_transaction_count"],
        "method": "linear_trend",
        "lookback_weeks": 4
    }
}
```

---

## 기술 스택

| 역할 | 기술 |
|------|------|
| Web framework | FastAPI |
| LLM | OpenAI GPT (`langchain-openai`) |
| Agent orchestration | LangGraph (StateGraph) |
| DB (async) | MongoDB — `motor` |
| Vector DB | Qdrant |
| Task queue | Celery + Redis |
| PPT 생성 | python-pptx |

- LangGraph pipeline은 Celery task 안에서 실행됨
- `POST /analysis/run` → Celery 등록 → `job_id` 즉시 반환 → `GET /analysis/status/{job_id}` 폴링

---

## 구현 현황

### 완료된 파일

| 파일 | 상태 | 비고 |
|------|------|------|
| `agents/supervisor.py` | ✅ 완료 | deterministic, LLM 없음 |
| `agents/schema_mapping_agent.py` | ✅ 완료 | 표준 GA4 baseline + LLM(불일치 시만) |
| `agents/funnel_agent.py` | ✅ 완료 | 유저 단위 집계, breakdown 포함 |
| `agents/cohort_agent.py` | ✅ 완료 | first_purchase_week 코호트, retention/revenue |
| `agents/journey_agent.py` | ✅ 완료 | 세션 시퀀스, top-N 경로, transition matrix |
| `agents/performance_agent.py` | ✅ 완료 | 주간 KPI + daily/source/device/category + WoW |
| `agents/anomaly_agent.py` | ✅ 완료 | Z-score + LLM 한국어 해석 |
| `agents/prediction_agent.py` | ✅ 완료 | linear least-squares + LLM 한국어 코멘트 |
| `agents/_ga4_utils.py` | ✅ 완료 | 공용 파싱 유틸 (모든 agent에서 import) |

### 미완료 (DB 연결 후 작업 필요)

- `graph/pipeline.py` — LangGraph StateGraph 정의 (supervisor → schema_mapping → 6개 병렬 → insight)
- `db/mongo.py` — motor AsyncIOMotorClient 연결
- `core/config.py` — BaseSettings 실제 구현 (현재 placeholder)
- 각 agent의 `raw_logs` 처리 → MongoDB aggregation pipeline으로 교체

---

## 파싱 유틸 (_ga4_utils.py)

GA4 raw log에서 필드를 추출하는 함수들을 `app/agents/_ga4_utils.py`에 집중.
**agent 파일에서 직접 파싱 로직 구현 금지** — 반드시 이 모듈에서 import.

```python
from app.agents._ga4_utils import (
    get_event_param, get_session_id,
    get_traffic_source, get_device_category,
    get_purchase_revenue, get_transaction_id,
    in_range, shift_days, date_to_iso_week, date_to_weekday, week_offset,
)
```

---

## state 키 실제 명세 (context_agent.py 기준)

CLAUDE.md 초안과 models.py 일부 표기가 다름. **context_agent.py가 정답**.

| 키 | 타입 | 생성자 |
|----|------|--------|
| `domain_context` | `dict` (DomainContext.model_dump()) | context_agent |
| `field_mapping` | `dict` | schema_mapping_agent |
| `funnel_metrics` | `dict` | funnel_agent |
| `cohort_metrics` | `dict` | cohort_agent |
| `journey_metrics` | `dict` | journey_agent |
| `performance_metrics` | `dict` | performance_agent |
| `anomaly_metrics` | `dict` | anomaly_agent |
| `prediction_metrics` | `dict` | prediction_agent |

각 agent config 접근: `state["domain_context"]["funnel_config"]["steps"]` 형태.

---

## 프로젝트 구조

```
K-PatternHunters/
├── backend/
│   ├── .venv/                       # Python 가상환경 (requirements.txt 기준)
│   ├── main.py
│   └── app/
│       ├── agents/
│       │   ├── _ga4_utils.py        # 공용 GA4 파싱 유틸 ← 신규
│       │   ├── supervisor.py
│       │   ├── schema_mapping_agent.py
│       │   ├── funnel_agent.py
│       │   ├── cohort_agent.py
│       │   ├── journey_agent.py
│       │   ├── performance_agent.py
│       │   ├── anomaly_agent.py
│       │   ├── prediction_agent.py
│       │   ├── context_agent.py     ← 타팀
│       │   ├── insight_agent.py     ← 타팀
│       │   └── ppt_agent.py         ← 타팀
│       ├── core/
│       │   ├── config.py            # BaseSettings (pydantic-settings, .env 로드)
│       │   └── models.py            # Pydantic v2 모델
│       ├── db/
│       │   ├── mongo.py             # motor AsyncIOMotorClient (미완료)
│       │   └── qdrant.py
│       ├── graph/
│       │   └── pipeline.py          # LangGraph StateGraph 정의 (미완료)
│       ├── routers/
│       │   ├── analysis.py          # POST /analysis/run
│       │   └── status.py            # GET /analysis/status/{job_id}
│       └── tools/
│           ├── rag_tool.py
│           └── web_search_tool.py
├── frontend/                        # Vue 3 (타팀)
├── docs/
│   ├── architecture.md              # 전체 설계 상세
│   └── agents/                      # Agent별 스펙 문서
│       ├── supervisor.md
│       ├── schema_mapping.md
│       ├── funnel.md
│       ├── cohort.md
│       ├── journey.md
│       ├── performance.md
│       ├── anomaly.md
│       └── prediction.md
├── docker-compose.yml
└── .env                             # OPENAI_API_KEY, MONGODB_URI, QDRANT_URL, REDIS_URL
```

---

## 타팀 인터페이스 경계

| agent | 담당 | 우리가 넘겨줄 것 |
|-------|------|-----------------|
| `insight_agent` | 6개 분석 결과 종합 → 내러티브 | `*_metrics` 6개 키 전부 state에 있으면 됨 |
| `ppt_agent` | insight_report + Qdrant 저번주 비교 → PPT | `insight_report` dict (타팀 생성) |

**역할 구분 주의**: `anomaly_agent`/`prediction_agent`의 LLM 코멘트는 **지표별 단편 해석**이고, `insight_agent`는 **전체 종합 해석**임. 겹치는 게 아니라 insight_agent의 input 데이터로 들어가는 구조.

**state 키 이름 협의 필요**: 우리는 `funnel_metrics`, `cohort_metrics`... 로 쓰는데, 타팀이 `funnel_result`, `cohort_result`... 를 기대할 수 있음. 타팀 구현 시작 전에 맞춰볼 것.

---

## 개발 시 주의사항

1. **agent 구현 전에 반드시 `docs/agents/{agent명}.md` 먼저 확인** — input/output 스펙이 거기 있음
2. **볼륨 안전**: raw document 전체 메모리 로드 절대 금지, MongoDB aggregation pipeline으로 처리
3. **LLM 호출 최소화**: Schema Mapping(불일치 시만), Anomaly(이상값 있을 때만), Prediction(결과 코멘트)
4. **타팀 파일 수정 금지**: `context_agent.py`, `insight_agent.py`, `ppt_agent.py`
5. **state 기반 데이터 전달**: 중간 결과는 LangGraph state로만, DB 저장은 최종 결과만
6. **branch**: 현재 작업 브랜치 `backend_jy`
7. **GA4 파싱은 `_ga4_utils.py`에서만**: agent 파일에 파싱 로직 중복 구현 금지
8. **테스트**: `cd backend && python test_agents.py` — DB 없이 전 agent 동작 확인 가능

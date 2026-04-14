# K-PatternHunters — System Architecture

## Overview

Weekly behavioral pattern analysis system for GA4 ecommerce data.
Raw event logs stored in MongoDB → automated multi-agent analysis → PPT report.

**Input:** Weekly raw GA4 event logs (MongoDB) + domain category  
**Output:** Behavioral pattern analysis results + auto-generated PPT report

---

## Data Source

- **Origin:** GA4 BigQuery `ga4_obfuscated_sample_ecommerce` sample dataset
- **Storage:** MongoDB (`raw_logs` collection)
- **Ingestion cadence:** Weekly batch load
- **Weekly range key:** `event_date` field (format: `YYYYMMDD`, e.g. `20210101`~`20210107`)
- **Document structure:** GA4 BigQuery export nested structure (원본 그대로)
  - `event_params[]` 배열 필드 포함
  - `items[]` 배열 필드 포함
- **Assumed volume:** 수만~수십만 documents / week → agent는 집계 쿼리 기반으로 접근 (raw document 전체 메모리 로드 금지)

---

## Agent Pipeline

```
[START]
   │
context_agent          ← (타팀 담당) RAG + web search → domain context 생성
   │
supervisor             ← context 수신, schema mapping 실행 후 분석 agent 병렬 팬아웃
   │
schema_mapping_agent   ← raw GA4 스키마 → normalized field mapping 생성
   │
   ├── funnel_agent
   ├── cohort_agent
   ├── journey_agent       (병렬 실행)
   ├── performance_agent
   ├── anomaly_agent
   └── prediction_agent
          │
   insight_agent       ← (타팀 담당) 전체 분석 결과 종합 해석
          │
   ppt_agent           ← (타팀 담당) 저번 주 보고서 비교 + PPT 생성
          │
        [END]
```

**담당 범위 (이 레포):**
- Supervisor Agent
- Schema Mapping Agent
- Funnel / Cohort / Journey / Performance / Anomaly / Prediction Agent

---

## LangGraph State (PipelineState)

모든 agent는 LangGraph `StateGraph`의 노드로 등록되며, 공유 state dict를 통해 데이터를 전달한다.
중간 결과는 MongoDB에 저장하지 않고 state로만 전달하며, 최종 결과만 저장한다.

```python
class PipelineState(TypedDict):
    # Input
    week_start: str           # e.g. "20210101"
    week_end: str             # e.g. "20210107"
    domain: str               # e.g. "ecommerce"

    # Context Agent output (타팀)
    context: AnalysisContext

    # Schema Mapping Agent output
    field_mapping: dict       # raw field → normalized field name mapping

    # Analysis Agent outputs (병렬)
    funnel_result: dict
    cohort_result: dict
    journey_result: dict
    performance_result: dict
    anomaly_result: dict
    prediction_result: dict

    # Downstream (타팀)
    insight: dict
    ppt_url: str
```

---

## Context Agent Output Schema

Context Agent(타팀)가 생성하여 Supervisor에게 전달하는 `AnalysisContext` 구조.
각 분석 Agent는 `state["context"]` 에서 해당 섹션을 읽어 동작한다.

```python
class AnalysisContext(TypedDict):
    domain: str

    funnel: FunnelContext
    cohort: CohortContext
    journey: JourneyContext
    performance: PerformanceContext
    anomaly: AnomalyContext
    prediction: PredictionContext
```

### FunnelContext
```python
class FunnelContext(TypedDict):
    steps: list[str]
    # e.g. ["session_start", "view_item", "add_to_cart", "begin_checkout", "purchase"]
    key_metric: str
    # e.g. "conversion_rate"
```

### CohortContext
```python
class CohortContext(TypedDict):
    definition: str
    # e.g. "first_purchase_week" — user_pseudo_id 기준 첫 구매 발생 주차
    metrics: list[str]
    # e.g. ["retention_rate", "revenue_per_user"]
```

### JourneyContext
```python
class JourneyContext(TypedDict):
    top_n_paths: int
    # e.g. 10
    max_depth: int
    # e.g. 5 — 세션 내 이벤트 시퀀스 최대 depth
    entry_events: list[str]
    # e.g. ["session_start", "page_view"]
    exit_events: list[str]
    # e.g. ["purchase", "session_end"]
```

### PerformanceContext
```python
class PerformanceContext(TypedDict):
    kpis: list[str]
    # e.g. ["total_revenue", "transaction_count", "arpu", "session_count", "conversion_rate", "bounce_rate"]
    breakdowns: list[str]
    # e.g. ["traffic_source", "device_category"]
```

### AnomalyContext
```python
class AnomalyContext(TypedDict):
    target_metrics: list[str]
    # e.g. ["daily_revenue", "daily_session_count", "daily_conversion_rate"]
    method: str
    # e.g. "zscore"
    threshold: float
    # e.g. 2.0
```

### PredictionContext
```python
class PredictionContext(TypedDict):
    targets: list[str]
    # e.g. ["next_week_revenue", "next_week_transaction_count"]
    method: str
    # e.g. "linear_trend"
    lookback_weeks: int
    # e.g. 4 — 직전 N주 데이터 기반 예측
```

---

## Tech Stack

| 역할 | 기술 |
|------|------|
| Web framework | FastAPI |
| LLM | OpenAI GPT (langchain-openai) |
| Agent orchestration | LangGraph (StateGraph) |
| Database | MongoDB (motor - async) |
| Vector DB | Qdrant |
| Task queue | Celery + Redis |
| PPT generation | python-pptx |

---

## Execution Flow

1. `POST /analysis/run` 요청 수신 → Celery task 등록 → `job_id` 즉시 반환
2. Celery worker가 LangGraph pipeline 실행
3. `context_agent` (타팀) → `AnalysisContext` 생성
4. `supervisor` → `schema_mapping_agent` 실행 → field mapping 확정
5. `supervisor` → 6개 분석 agent 병렬 팬아웃
6. 병렬 분석 완료 → `insight_agent` (타팀) → `ppt_agent` (타팀)
7. 최종 결과 MongoDB 저장, `GET /analysis/status/{job_id}` 로 폴링 가능

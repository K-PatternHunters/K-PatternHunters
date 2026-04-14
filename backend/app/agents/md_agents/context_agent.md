# context_agent — 개발 노트

## 역할

주간 raw log 데이터와 도메인 카테고리를 입력받아, 하위 에이전트들이 분석을 수행하고
PPT를 생성할 때 활용할 **구조화된 도메인 컨텍스트**를 생성하는 에이전트.

---

## 컨텍스트 포맷 결정

### 선택: Pydantic 모델 (`DomainContext`) → `.model_dump()` → LangGraph state dict

| 후보 포맷 | 장점 | 단점 | 결론 |
|---|---|---|---|
| 자유 형식 문자열 (마크다운/자연어) | 생성 유연성 | 하위 에이전트가 파싱 필요, 오류 위험 | ❌ |
| 단순 dict | 구현 빠름 | 스키마 없음, 필드 누락 감지 불가 | ❌ |
| **Pydantic 모델 → dict** | 타입 안전, 명확한 계약, LangGraph state와 호환 | 초기 스키마 설계 비용 | **✅ 채택** |
| JSON 스키마 문자열 (직렬화) | 범용성 | 불필요한 역직렬화 비용 | ❌ |

**Pydantic을 선택한 이유:**
- LangGraph state는 `TypedDict`(dict) 기반이므로 `.model_dump()`로 자연스럽게 통합됨
- 하위 에이전트들이 `state["domain_context"]["recommended_sub_agents"]` 처럼 필드에 직접 접근 가능
- Supervisor가 `recommended_sub_agents` 필드로 라우팅 결정을 코드로 처리 가능
- 스키마 변경 시 `DomainContext` 모델 하나만 수정하면 전체 파이프라인에 전파됨

---

## DomainContext 필드 구조

```
DomainContext
│
│  [도메인 개요]
├── domain                    : str              # 도메인 카테고리 (e-commerce, fintech 등)
├── domain_summary            : str              # 도메인 행동 패턴 요약
├── analysis_priorities       : list[str]        # 우선순위 순 분석 타입 목록
├── recommended_sub_agents    : list[str]        # 실행할 하위 에이전트 목록
│
│  [해석 가이드 & 벤치마크]
├── key_metrics               : dict[str, str]   # KPI명 -> 정의
├── interpretation_guidelines : dict[str, str]   # 분석 타입 -> 해석 방법
├── industry_benchmarks       : dict[str, Any]   # 업계 벤치마크 수치
│
│  [필수 분석 설정 — 각 하위 에이전트에 직접 전달]
├── funnel_config
│   └── steps                 : list[str]        # 전환 퍼널 이벤트 순서
│
├── cohort_config
│   ├── cohort_basis          : str              # 코호트 기준 이벤트/시점
│   ├── user_key              : str              # 사용자 식별 필드명
│   └── metrics               : list[str]        # 주차별 집계 지표
│
├── journey_config
│   ├── top_n                 : int              # 경로별 상위 N개
│   ├── max_depth             : int              # 경로 최대 이벤트 깊이
│   └── split_by_outcome      : bool             # 전환/이탈 경로 분리 여부
│
├── performance_config
│   ├── kpis                  : list[str]        # 측정할 KPI 목록
│   └── breakdowns            : list[str]        # 크로스탭 차원 목록
│
├── anomaly_config
│   ├── target_metrics        : list[str]        # 이상 감지 대상 지표
│   ├── method                : str              # 탐지 방식 (z_score 등)
│   └── threshold             : float            # Z-score 임계값
│
├── prediction_config
│   ├── targets               : list[str]        # 예측 대상 지표
│   ├── method                : str              # 예측 방식 (linear_trend 등)
│   └── lookback_weeks        : int              # 학습 윈도우 (주 단위)
│
│  [스키마 힌트 & 참조]
├── log_schema_hints          : dict[str, str]   # raw 필드명 -> 의미
├── rag_references            : list[str]        # RAG에서 검색된 참고 문서
└── search_references         : list[str]        # 웹 검색 결과 참조
```

### 기본값 (e-commerce 도메인 기준)

| 설정 | 기본값 |
|---|---|
| `funnel_config.steps` | `session_start → view_item → add_to_cart → begin_checkout → purchase` |
| `cohort_config.cohort_basis` | `first_purchase_week` |
| `cohort_config.user_key` | `user_pseudo_id` |
| `cohort_config.metrics` | `retention_rate`, `avg_revenue` |
| `journey_config.top_n` | `10` |
| `journey_config.max_depth` | `5` |
| `journey_config.split_by_outcome` | `true` |
| `performance_config.kpis` | `total_revenue`, `transaction_count`, `arpu`, `session_count`, `conversion_rate`, `bounce_rate` |
| `performance_config.breakdowns` | `traffic_source`, `device_category` |
| `anomaly_config.target_metrics` | `daily_revenue`, `daily_session_count`, `daily_conversion_rate` |
| `anomaly_config.method` | `z_score` |
| `anomaly_config.threshold` | `2.0` |
| `prediction_config.targets` | `next_week_revenue`, `next_week_transaction_count` |
| `prediction_config.method` | `linear_trend` |
| `prediction_config.lookback_weeks` | `4` |

### 하위 에이전트별 활용 필드

| 에이전트 | 주로 읽는 필드 |
|---|---|
| supervisor | `recommended_sub_agents`, `analysis_priorities` |
| funnel_agent | `funnel_config`, `interpretation_guidelines["funnel"]`, `industry_benchmarks` |
| cohort_agent | `cohort_config`, `interpretation_guidelines["cohort"]` |
| journey_agent | `journey_config`, `log_schema_hints` |
| performance_agent | `performance_config`, `key_metrics`, `industry_benchmarks` |
| anomaly_agent | `anomaly_config`, `interpretation_guidelines["anomaly"]` |
| prediction_agent | `prediction_config`, `interpretation_guidelines["prediction"]` |
| schema_mapping_agent | `log_schema_hints` |
| insight_agent | `domain_summary`, `key_metrics`, `industry_benchmarks` |
| ppt_agent | `domain_summary`, `domain`, `industry_benchmarks` |

---

## 처리 흐름

```
state["domain_description"]
state["raw_logs"]
        │
        ├─── asyncio.gather ──┬── _try_rag()         # Qdrant RAG (미구현 시 [] 반환)
        │                     └── _try_web_search()   # Tavily 웹 검색 (미구현 시 [] 반환)
        │
        ▼
  ChatOpenAI.with_structured_output(DomainContext, method="function_calling")
  (gpt-4o-mini, temperature=0)
        │
        ▼
  domain_context.model_dump()
        │
        ▼
  state["domain_context"]  →  supervisor로 전달
```

---

## 트러블슈팅

### IDE 경고: `langchain_openai` import 확인 불가
- **원인**: VSCode Python 인터프리터가 `.venv`를 바라보지 않아 패키지를 찾지 못함
- **해결**: `Cmd+Shift+P` → `Python: Select Interpreter` → `backend/.venv/bin/python` 선택
- **코드 자체는 정상** — `requirements.txt`에 `langchain-openai`가 명시되어 있음

### `Any` 미사용 import 경고
- **원인**: `typing.Any`를 `context_agent.py`에서 import했으나 실제 사용처가 없음
  (`Any`는 `models.py`의 `DomainContext`에서만 사용)
- **해결**: `context_agent.py`에서 `from typing import Any` 제거 완료

### `openai.BadRequestError: Invalid schema for response_format` (테스트 실패)
- **원인**: OpenAI Structured Outputs strict mode는 모든 object 타입에 `additionalProperties: false`를 요구.
  `dict[str, Any]` 같은 자유형 타입은 이 조건을 자동으로 만족시킬 수 없어 400 에러 발생.
- **에러 메시지**: `In context=('properties', 'industry_benchmarks'), 'additionalProperties' is required to be supplied and to be false`
- **해결**: `.with_structured_output(DomainContext, method="function_calling")`으로 변경.
  `function_calling` 방식은 strict mode를 사용하지 않아 `dict[str, Any]` 필드를 허용함.
- **동일 이슈**: `insight_agent.py`의 `InsightReport`에도 동일하게 적용

---

## 미구현 의존성 (향후 작업)

| 도구 | 현재 상태 | 영향 |
|---|---|---|
| `rag_tool.rag_search` | `NotImplementedError` | context 생성은 정상 동작, `rag_references` 빈 리스트 |
| `web_search_tool.web_search` | `NotImplementedError` | context 생성은 정상 동작, `search_references` 빈 리스트 |
| `config.get_settings()` | OPENAI_API_KEY placeholder | 실제 키 주입 필요 |

두 도구 모두 `NotImplementedError`를 `try/except`로 처리하여
**도구 미구현 상태에서도 LLM 기반 context 생성은 정상 작동**함.

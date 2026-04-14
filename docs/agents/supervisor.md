# Supervisor Agent

## 역할

Context Agent(타팀)로부터 `AnalysisContext`를 수신하고, 분석 파이프라인 전체를 조율한다.

1. `schema_mapping_agent` 를 먼저 실행하여 field mapping 확정
2. 6개 분석 agent를 병렬로 팬아웃
3. 분석 결과를 state에 취합하여 downstream(insight_agent)으로 전달

---

## Input (state에서 읽는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `week_start` | str | 분석 대상 주 시작일 (`YYYYMMDD`) |
| `week_end` | str | 분석 대상 주 종료일 (`YYYYMMDD`) |
| `domain` | str | 도메인 카테고리 (e.g. `"ecommerce"`) |
| `context` | AnalysisContext | Context Agent가 생성한 분석 파라미터 전체 |

## Output (state에 쓰는 값)

없음. Supervisor는 라우팅만 담당하며 결과값을 직접 생성하지 않는다.

---

## 실행 순서

```
supervisor
   │
   ├─[1]─ schema_mapping_agent   ← 완료 후 field_mapping 확정
   │
   └─[2]─ 병렬 팬아웃
            ├── funnel_agent
            ├── cohort_agent
            ├── journey_agent
            ├── performance_agent
            ├── anomaly_agent
            └── prediction_agent
```

- schema_mapping_agent는 반드시 분석 agent들보다 먼저 완료되어야 한다
- 분석 6개 agent는 LangGraph 병렬 브랜치로 동시 실행
- 모든 분석 agent 완료 후 insight_agent로 진행

---

## 라우팅 방식

Deterministic. LLM 호출 없음.
Context Agent가 이미 도메인 판단을 완료한 상태이므로, Supervisor는 항상 6개 agent 전부 실행한다.

---

## LangGraph 구현 포인트

- `StateGraph`에서 supervisor 노드는 단순 pass-through 역할
- `schema_mapping_agent` → `[funnel, cohort, journey, performance, anomaly, prediction]` 병렬 엣지
- 병렬 브랜치 종료 후 join → `insight_agent`

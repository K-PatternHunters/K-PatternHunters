# Pipeline Refactor 완료 기록

> 작업일: 2026-04-14
> 브랜치: `backend_jy`
> 참고 문서: [refactor_pipeline.md](refactor_pipeline.md)

---

## 한 일

`refactor_pipeline.md`에 정의된 방향대로 전체 리팩토링 완료.
핵심 원칙: **집계는 MongoDB에서, 통계/LLM은 Python에서**

### 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `app/agents/_ga4_utils.py` | `PREPROCESS_STAGE` 상수 추가. `revenue` (`purchase_revenue_in_usd` 우선), `transaction_id_clean` (`(not set)` → null 정규화) |
| `app/routers/analysis.py` | `raw_logs` 전량 로드 블록 제거 (`to_list`, `_prepare_doc`, `_bq_int64_to_int`, `_make_param_value`). `initial_state`에서 `raw_logs` 제거 |
| `app/core/models.py` | `PipelineState`에서 `raw_logs`, `log_ids`, `field_mapping`, `normalized_logs`, `sub_agents_plan` 제거 |
| `app/graph/pipeline.py` | `schema_mapping_agent` import/노드/엣지 제거. 토폴로지: `context_agent → analysis_dispatcher → insight_agent → ppt_agent` |
| `app/agents/funnel_agent.py` | Python 루프 → MongoDB `$group` + `$addToSet` + `$facet` (device/source 브레이크다운) |
| `app/agents/performance_agent.py` | Python 루프 → `$facet`으로 daily/source/device/category/bounce 한 번에 집계. WoW는 prior week 별도 aggregation 호출 |
| `app/agents/cohort_agent.py` | Python 루프 → `$group`으로 유저별 첫구매일 + 구매이력 수집. 리텐션/매출 계산은 Python 유지 |
| `app/agents/journey_agent.py` | Python 루프 → `$sort` + `$group` + `$push` + `$slice`로 세션 경로 수집. 경로 통계/transition matrix는 Python 유지 |
| `app/agents/anomaly_agent.py` | Python 루프 → `$group`으로 일별 session/revenue/transaction 집계. Z-score 계산 + LLM 해석은 Python 유지 |
| `app/agents/prediction_agent.py` | Python 루프 → `$group`으로 날짜별 구매 집계 후 Python에서 주별 롤업. 선형 추세 + LLM 코멘트는 Python 유지 |

### 제거된 것

- `schema_mapping_agent` — 파이프라인에서 완전 제거 (파일은 보존)
- `PipelineState.raw_logs` — 에이전트가 MongoDB에서 직접 집계하므로 불필요
- `analysis.py`의 임시 헬퍼 함수들 (`_bq_int64_to_int`, `_make_param_value`, `_prepare_doc`)

---

## 테스트 방법

### 사전 준비

```bash
cd backend
source .venv/bin/activate

# MongoDB, Redis가 실행 중인지 확인
docker-compose up -d mongo redis

# .env에 OPENAI_API_KEY 설정 확인
cat .env | grep OPENAI_API_KEY
```

### 1. 단위 테스트 (기존 — 현재 raw_logs 기반, 리팩토링 후 미적용)

> **주의**: 기존 `tests/`의 단위 테스트는 `raw_logs`를 fixture로 주입하는 방식이라
> 리팩토링 후 에이전트와 맞지 않음. E2E 테스트로 검증하거나 테스트 재작성 필요.

### 2. E2E API 테스트 (권장)

서버 실행:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

분석 요청 (1주치 데이터 — 297,357건):

```bash
curl -s -X POST http://localhost:8000/analysis/run \
  -H "Content-Type: application/json" \
  -d '{
    "domain_description": "GA4 e-commerce 패션/의류 쇼핑몰",
    "week_start": "20210115",
    "week_end": "20210121"
  }' | python3 -m json.tool
```

응답에서 `job_id` 확인 후 상태 폴링:

```bash
JOB_ID="<위에서 받은 job_id>"

# 상태 확인 (status: pending → running → done)
curl -s http://localhost:8000/analysis/status/$JOB_ID | python3 -m json.tool
```

### 3. 기대 결과

| 에이전트 | 기대 결과 | 비고 |
|---|---|---|
| funnel | steps 5개, user_count > 0 | session_start부터 purchase까지 |
| performance | revenue > 0, session_count > 0 | daily_breakdown 7개 |
| cohort | cohorts 리스트 비어있지 않음 | purchase 유저 기준 |
| journey | total_sessions > 0 | 약 35,000 세션 예상 |
| anomaly | 베이스라인 부족 경고 출력 (정상) | 샘플 데이터 17일치 한계 |
| prediction | skipped 또는 데이터 부족 경고 (정상) | 4주 lookback이지만 최대 17일치 |

전체 파이프라인 완료 기준: `status == "done"`, `2분 이내`

### 4. 에이전트별 aggregation 개별 확인 (MongoDB shell)

MongoDB에 직접 접속해서 aggregation 결과를 확인할 수 있다.

```bash
docker exec -it <mongo-container> mongosh customer_behavior
```

funnel 예시:

```js
db.raw_logs.aggregate([
  { $match: { event_date: { $gte: "20210115", $lte: "20210121" }, event_name: { $in: ["session_start","view_item","add_to_cart","begin_checkout","purchase"] } } },
  { $addFields: { revenue: { $ifNull: ["$ecommerce.purchase_revenue_in_usd", 0] } } },
  { $group: { _id: "$event_name", users: { $addToSet: "$user_pseudo_id" } } },
  { $project: { event_name: "$_id", user_count: { $size: "$users" }, _id: 0 } }
])
```

performance 예시:

```js
db.raw_logs.aggregate([
  { $match: { event_date: { $gte: "20210115", $lte: "20210121" } } },
  { $addFields: { revenue: { $ifNull: ["$ecommerce.purchase_revenue_in_usd", 0] } } },
  { $group: { _id: null, sessions: { $addToSet: { u: "$user_pseudo_id", s: "$ga_session_id" } }, revenue: { $sum: "$revenue" } } },
  { $project: { session_count: { $size: "$sessions" }, revenue: 1, _id: 0 } }
])
```

### 5. 성능 기준

| 항목 | 목표 |
|---|---|
| 각 에이전트 aggregation | 1~3초 |
| 전체 파이프라인 (LLM 포함) | 2분 이내 |
| `/analysis/status` 응답 | 파이프라인 실행 중에도 즉시 응답 |

이전에는 `raw_logs` 전량 로드만 수십 초 blocking이었으나, 리팩토링 후 각 에이전트가 필요한 집계 결과(수십~수백 rows)만 가져오므로 개선됨.

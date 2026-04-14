# Pipeline Refactor 계획

> 작성일: 2026-04-14  
> 작성 배경: Docker 환경에서 E2E 테스트 중 발견된 성능/정확성 문제 전수 정리

---

## 1. 문제 정의

### 1-1. 근본 문제: raw_logs 전량 Python 로드

```
POST /analysis/run
  └─ MongoDB에서 raw_logs 전량 조회 (686,810건)
       └─ Python 메모리로 전부 올림 (to_list)
            └─ 각 에이전트가 루프 돌면서 집계
```

- **`to_list()` 수십 초 blocking** → async event loop 점유 → `/analysis/status` 등 다른 요청도 응답 불가
- 에이전트 6개가 동일한 raw_logs를 각자 순회 → 중복 처리
- `to_list(length=100_000)` limit → 데이터 잘림 → funnel/journey/performance 집계 결과 0 반환
- limit을 500,000으로 올려도 근본 해결 안 됨 — 문제가 구조 자체에 있음

### 1-2. 데이터 포맷 불일치

#### event_params_flat

MongoDB에 `event_params` 배열이 아닌 `event_params_flat` dict으로 저장됨.
`_ga4_utils.get_session_id()`는 `event_params` 배열을 기대 → session_id 파싱 실패.

`analysis.py`의 `_prepare_doc()`이 재조립하도록 수정했으나, 근본적으로 aggregation 전환 시 불필요해짐.

#### INT64 wire format

`ga_session_id`, `event_timestamp`가 BigQuery INT64 wire format으로 저장됨:

```json
{"high": 1, "low": 279927387, "unsigned": false}
```

Python에서 숫자로 쓸 때는 변환 필요:
```python
def _bq_int64_to_int(v: dict) -> int:
    high = v.get("high", 0) or 0
    low  = v.get("low",  0) or 0
    if low < 0:
        low += 1 << 32
    return (high << 32) | low
```

aggregation group key로 쓸 때는 변환 없이 그대로 써도 됨.

#### purchase_revenue 필드

```json
"ecommerce": {
  "purchase_revenue": null,          // 대부분 null — 사용 금지
  "purchase_revenue_in_usd": 89000   // 실제 값은 여기
}
```

`_ga4_utils.get_purchase_revenue()`가 `purchase_revenue`를 먼저 보도록 되어 있어서
실제 매출이 0으로 집계됨. aggregation에서는 반드시 `purchase_revenue_in_usd` 사용.

#### user_pseudo_id 형태

```
"1003157.8232583593"  // 부동소수점 문자열
```

group key로 그대로 쓰면 됨. 변환 불필요.

### 1-3. 샘플 데이터 한계 (코드 문제 아님)

| 항목 | 필요 | 실제 |
|---|---|---|
| 전체 기간 | - | 20210115~20210131 (17일치) |
| prediction lookback | 4주 (28일) | 최대 17일 → 항상 경고 |
| anomaly 베이스라인 | 7일 | week_start=20210122 이상일 때만 일부 가능 |
| purchase 건수 | - | 546건 (전체의 0.08%) |

→ prediction/anomaly 경고는 샘플 데이터 한계. 코드로 해결 불가, 경고 메시지 유지하고 있는 데이터로 최선의 결과 반환하는 현재 로직 유지.

---

## 2. MongoDB 실제 구조

### 2-1. raw_logs 도큐먼트 구조

```json
{
  "_id": "542704c52a430dc2d6ce06f5fe1e0dea",
  "event_date": "20210115",
  "event_datetime": "2021-01-15T03:43:02.563Z",
  "event_name": "purchase",
  "user_pseudo_id": "1003157.8232583593",
  "ga_session_id": {"high": 1, "low": 279927387, "unsigned": false},
  "ga_session_number": 6,
  "event_timestamp": {"high": 375016, "low": 727086844, "unsigned": false},
  "event_params_flat": {
    "ga_session_id": {"high": 1, "low": 279927387, "unsigned": false},
    "ga_session_number": 6,
    "source": "shop.googlemerchandisestore.com",
    "medium": "referral",
    "page_title": "Checkout Confirmation"
  },
  "ecommerce": {
    "purchase_revenue": null,
    "purchase_revenue_in_usd": 89000,
    "transaction_id": "T001",
    "unique_items": 1
  },
  "device": {"category": "desktop"},
  "traffic_source": {"source": "google", "medium": "cpc"},
  "geo": {"country": "KR", "city": "Seoul"}
}
```

### 2-2. 인덱스 현황 (기존 — 활용 가능)

```
{ event_date: 1 }
{ event_date: -1 }
{ event_datetime: 1 }
{ event_name: 1, event_date: 1 }
{ event_date: 1, event_name: 1 }
{ user_pseudo_id: 1, ga_session_id: 1, event_timestamp: 1 }
{ user_pseudo_id: 1, user_first_touch_timestamp: 1 }
{ traffic_source.source: 1 }
{ traffic_source.medium: 1 }
{ device.category: 1 }
{ ecommerce.transaction_id: 1 }
```

### 2-3. 날짜별 건수

```
20210115: 40,405   20210122: 49,922
20210116: 30,261   20210123: 34,322
20210117: 27,064   20210124: 31,702
20210118: 32,358   20210125: 41,718
20210119: 50,474   20210126: 42,232
20210120: 64,109   20210127: 48,665
20210121: 52,686   20210128: 43,131
                   20210129: 40,877
                   20210130: 30,395
                   20210131: 26,489
```

1주치(20210115~20210121): 297,357건

---

## 3. 해결 방향

### 핵심 원칙

> **집계는 MongoDB에서, 통계/LLM은 Python에서**

- raw_logs를 Python으로 올리지 않는다
- 각 에이전트는 MongoDB aggregation으로 필요한 집계 결과만 가져온다
- Python으로 넘어오는 건 에이전트당 수십~수백 rows

### schema_mapping_agent 제거

aggregation 전환 후 schema_mapping_agent는 역할이 없어짐.

- GA4 BigQuery export 포맷은 표준이고 인덱스도 그 구조 기준으로 설계됨
- 각 에이전트가 aggregation 필드명을 고정으로 가짐
- `domain_context`의 파라미터(`funnel_config.steps` 등)만 받아서 에이전트가 스스로 aggregation 구성
- **schema_mapping_agent는 파이프라인에서 제거, pipeline.py 엣지도 제거**

### 전처리: `$addFields` 공통 스테이지

전처리를 ingest 시점이 아닌 aggregation 안에서 처리.
`_ga4_utils.py`에 공통 `$addFields` 스테이지를 상수로 정의하고 각 에이전트가 재사용.

```python
# app/agents/_ga4_utils.py 에 추가

# 각 에이전트 aggregation pipeline 첫 번째 스테이지로 삽입
PREPROCESS_STAGE = {
    "$addFields": {
        # purchase_revenue_in_usd 우선, fallback으로 purchase_revenue
        "revenue": {
            "$ifNull": [
                "$ecommerce.purchase_revenue_in_usd",
                { "$ifNull": ["$ecommerce.purchase_revenue", 0] }
            ]
        },
        # transaction_id "(not set)" → null 정규화
        "transaction_id_clean": {
            "$cond": [
                { "$in": ["$ecommerce.transaction_id", ["(not set)", "", None]] },
                None,
                "$ecommerce.transaction_id"
            ]
        }
    }
}
```

사용 예시:
```python
pipeline = [
    { "$match": { "event_date": { "$gte": week_start, "$lte": week_end } } },
    PREPROCESS_STAGE,   # ← 공통 전처리
    { "$group": { ... } }
]
col.aggregate(pipeline)
```

### 아키텍처 변경

```
현재:
  analysis.py
    └─ MongoDB 686,810건 전량 로드 → PipelineState.raw_logs
    └─ schema_mapping_agent (field_mapping 생성)
    └─ 각 에이전트가 Python 루프로 집계

변경 후:
  analysis.py
    └─ PipelineState에 raw_logs 없음 (week_start/week_end만 전달)
    └─ schema_mapping_agent 제거
    └─ 각 에이전트가 get_collection("raw_logs")로 직접 aggregation 실행
         └─ PREPROCESS_STAGE 삽입 후 집계
    └─ Python으로는 집계 결과(수십~수백 rows)만 받음
```

### pipeline.py 변경

```python
# 현재
context_agent → schema_mapping_agent → analysis_dispatcher → insight_agent → ppt_agent

# 변경 후
context_agent → analysis_dispatcher → insight_agent → ppt_agent
```

---

## 4. 에이전트별 Aggregation 설계

### 공통 사항

- `event_datetime` (ISO 문자열, 인덱스 있음)으로 정렬 — `event_timestamp` INT64 변환 불필요
- `ga_session_id` dict 그대로 group key로 사용 가능
- 매출은 반드시 `ecommerce.purchase_revenue_in_usd` 사용

---

### 4-1. Funnel Agent

**목표**: 이벤트 단계별 unique user 수 → 전환율/이탈율 계산

```js
// Python으로 넘어오는 rows: funnel_steps 수 (기본 5개)
db.raw_logs.aggregate([
  { $match: {
      event_date: { $gte: week_start, $lte: week_end },
      event_name: { $in: funnel_steps }
  }},
  { $group: {
      _id: "$event_name",
      users: { $addToSet: "$user_pseudo_id" }
  }},
  { $project: {
      event_name: "$_id",
      user_count: { $size: "$users" }
  }}
])

// 브레이크다운 (device/source) — $facet으로 추가
{ $facet: {
    by_device: [
      { $group: { _id: { event: "$event_name", device: "$device.category" },
                  users: { $addToSet: "$user_pseudo_id" } }},
      { $project: { event_name: "$_id.event", device: "$_id.device",
                    user_count: { $size: "$users" } }}
    ],
    by_source: [ ... ]
}}
```

전환율/이탈율 계산은 Python에서 (단순 비율 계산).

---

### 4-2. Performance Agent

**목표**: 주간 KPI + 일별/소스별/기기별/카테고리별 브레이크다운 + WoW

```js
// Python으로 넘어오는 rows: 일별 7개 + 소스별 수십 개 + 기기별 수 개
db.raw_logs.aggregate([
  { $match: { event_date: { $gte: week_start, $lte: week_end } } },
  { $facet: {
      // 일별
      daily: [
        { $group: {
            _id: "$event_date",
            sessions: { $addToSet: {u: "$user_pseudo_id", s: "$ga_session_id"} },
            revenue: { $sum: "$ecommerce.purchase_revenue_in_usd" },
            transactions: { $addToSet: "$ecommerce.transaction_id" }
        }},
        { $project: {
            date: "$_id",
            session_count: { $size: "$sessions" },
            revenue: 1,
            transaction_count: { $size: "$transactions" }
        }}
      ],
      // 소스별
      by_source: [
        { $group: {
            _id: "$traffic_source.source",
            sessions: { $addToSet: {u: "$user_pseudo_id", s: "$ga_session_id"} },
            revenue: { $sum: "$ecommerce.purchase_revenue_in_usd" }
        }},
        { $project: { source: "$_id", session_count: { $size: "$sessions" }, revenue: 1 } }
      ],
      // 기기별
      by_device: [
        { $group: {
            _id: "$device.category",
            sessions: { $addToSet: {u: "$user_pseudo_id", s: "$ga_session_id"} },
            revenue: { $sum: "$ecommerce.purchase_revenue_in_usd" }
        }},
        { $project: { device: "$_id", session_count: { $size: "$sessions" }, revenue: 1 } }
      ]
  }}
])
```

- **WoW**: prior week (`shift_days(week_start, -7)` ~ `shift_days(week_end, -7)`)로 동일 aggregation 별도 호출
- **bounce rate**: 세션당 이벤트 수 1개인 세션 → `$group` + `$sum: 1` 후 Python에서 필터
- **ARPU/CVR**: Python에서 계산 (단순 나눗셈)

---

### 4-3. Cohort Agent

**목표**: 사용자별 첫 구매 주 코호트 + 이후 재구매 리텐션/매출

```js
// Step 1: 사용자별 모든 구매 이력
// Python으로 넘어오는 rows: 구매 유저 수 (샘플 기준 소수)
db.raw_logs.aggregate([
  { $match: {
      event_name: "purchase",
      "ecommerce.purchase_revenue_in_usd": { $gt: 0 }
  }},
  { $group: {
      _id: "$user_pseudo_id",
      first_purchase_date: { $min: "$event_date" },
      purchases: { $push: {
          date: "$event_date",
          revenue: "$ecommerce.purchase_revenue_in_usd"
      }}
  }}
])
```

- 코호트 주(ISO week) 변환, 리텐션율/revenue_per_user 계산은 Python에서
- 날짜 범위 제한 없이 전체 기간 조회 (코호트 특성상 분석 주 이전 데이터도 필요)

---

### 4-4. Journey Agent

**목표**: 세션별 이벤트 시퀀스 → Top N 경로 + transition matrix

```js
// Python으로 넘어오는 rows: 세션 수 (~35,000건/주 — 많음, 아래 주의 참고)
db.raw_logs.aggregate([
  { $match: { event_date: { $gte: week_start, $lte: week_end } } },
  { $sort: { user_pseudo_id: 1, ga_session_id: 1, event_datetime: 1 } },
  { $group: {
      _id: { user: "$user_pseudo_id", session: "$ga_session_id" },
      path: { $push: "$event_name" }
  }},
  { $project: {
      path: { $slice: ["$path", max_depth] }  // max_depth=5
  }}
])
```

**주의: 35,000 rows도 많음** → 추가 최적화 검토
- Top N 경로 빈도는 aggregation 안에서 `$group`으로 미리 계산 가능
- transition matrix도 `$unwind` + `$group`으로 aggregation에서 처리 검토
- 최소한 경로 배열(path)만 받아서 Python에서 카운팅하는 현재 설계 유지하되, 결과 rows 수를 줄이는 방향으로

경로 빈도 집계, converted/churned 분류, transition matrix 계산은 Python에서.

---

### 4-5. Anomaly Agent

**목표**: 일별 지표 시계열 (현재 기간 + 베이스라인) → Z-score

```js
// Python으로 넘어오는 rows: 날짜 수 (최대 수십 rows)
db.raw_logs.aggregate([
  { $match: { event_date: { $gte: baseline_start, $lte: week_end } } },
  { $group: {
      _id: "$event_date",
      sessions: { $addToSet: { u: "$user_pseudo_id", s: "$ga_session_id" } },
      revenue: { $sum: "$ecommerce.purchase_revenue_in_usd" },
      transactions: { $addToSet: "$ecommerce.transaction_id" }
  }},
  { $project: {
      date: "$_id",
      session_count: { $size: "$sessions" },
      revenue: 1,
      transaction_count: { $size: "$transactions" },
      conversion_rate: {
          $cond: [
              { $gt: [{ $size: "$sessions" }, 0] },
              { $divide: [{ $size: "$transactions" }, { $size: "$sessions" }] },
              0
          ]
      }
  }},
  { $sort: { date: 1 } }
])
```

- `baseline_start`: `shift_days(week_start, -14)` (2주 전) — 샘플 데이터 17일치 한계 고려
- Z-score 계산 (평균/표준편차), LLM 해석은 Python에서
- 베이스라인 데이터 부족 경고는 유지 (데이터 한계, 코드로 해결 불가)

---

### 4-6. Prediction Agent

**목표**: 주별 시계열 집계 → 선형 추세 → 다음 주 예측

```js
// Python으로 넘어오는 rows: 날짜 수 (최대 17개 — 샘플 데이터 전체 기간)
db.raw_logs.aggregate([
  { $match: {
      event_name: "purchase",
      event_date: { $gte: lookback_start, $lte: week_end },
      "ecommerce.purchase_revenue_in_usd": { $gt: 0 }
  }},
  { $group: {
      _id: "$event_date",
      revenue: { $sum: "$ecommerce.purchase_revenue_in_usd" },
      transaction_count: { $sum: 1 }
  }},
  { $sort: { _id: 1 } }
])
```

- 날짜별 결과를 Python에서 ISO week 기준으로 롤업
- 선형 추세(least-squares), 신뢰구간, LLM 코멘트는 Python에서
- lookback 데이터 부족 시 `skipped` 반환 로직 유지 (샘플 데이터 한계)

---

## 5. 수정 파일 목록

### `app/routers/analysis.py`
```python
# 제거
- raw_logs 로드 전체 블록 (to_list, _prepare_doc, limit 등)
- _bq_int64_to_int()
- _make_param_value()
- _prepare_doc()
- timedelta import

# 변경
- initial_state에서 raw_logs 제거
```

### `app/core/models.py`
```python
# 제거
- PipelineState.raw_logs: list[dict]
- PipelineState.log_ids: list[str]  # 필요시 유지 가능
- PipelineState.field_mapping         # schema_mapping 제거에 따라
- PipelineState.normalized_logs       # 동일
- PipelineState.sub_agents_plan       # supervisor 미사용 확인 후
```

### `app/graph/pipeline.py`
```python
# 제거
- schema_mapping_agent 노드 등록
- context_agent → schema_mapping_agent 엣지
- schema_mapping_agent → analysis_dispatcher 엣지

# 변경
- context_agent → analysis_dispatcher 직접 연결
```

### `app/agents/_ga4_utils.py`
```python
# 추가
- PREPROCESS_STAGE: dict  # $addFields 공통 전처리 스테이지

# 유지 (journey 후처리 등 일부 여전히 필요)
- get_session_id(), in_range(), shift_days() 등

# 제거 또는 수정
- get_purchase_revenue(): PREPROCESS_STAGE로 대체되므로 제거 검토
```

### `app/agents/performance_agent.py`
- `_aggregate_week()` → MongoDB aggregation + PREPROCESS_STAGE
- prior week: 동일 aggregation, 날짜 범위만 변경
- Python: ARPU/CVR/bounce_rate 계산만

### `app/agents/funnel_agent.py`
- 루프 기반 집계 → MongoDB aggregation (`$group` + `$addToSet`) + PREPROCESS_STAGE
- 브레이크다운: `$facet`
- Python: 전환율/이탈율 계산만

### `app/agents/cohort_agent.py`
- purchase 필터 + 사용자별 첫구매 → MongoDB aggregation + PREPROCESS_STAGE
- Python: 코호트 리텐션/매출 계산 유지

### `app/agents/journey_agent.py`
- 세션 시퀀스 수집 → MongoDB aggregation (`$sort` + `$group` + `$push` + `$slice`)
- Python: 경로 빈도, transition matrix 유지
- 결과 rows 수 추가 최적화 검토 (Top N 경로를 aggregation 안에서 처리)

### `app/agents/anomaly_agent.py`
- `_aggregate_daily()` → MongoDB aggregation + PREPROCESS_STAGE
- Python: Z-score 계산, LLM 해석 유지

### `app/agents/prediction_agent.py`
- 구매 집계 → MongoDB aggregation + PREPROCESS_STAGE
- Python: 주별 롤업, 선형 추세, LLM 유지

### `app/agents/schema_mapping_agent.py`
- **파이프라인에서 제거** (파일 자체는 보존, 미사용 처리)

---

## 6. 테스트 시나리오

### 단위 테스트 (각 에이전트)

```bash
# 각 에이전트 aggregation 결과 검증
# - 건수 > 0 확인
# - 필드 구조 확인
# - Pydantic 모델 통과 확인
python -m pytest tests/test_performance_agent.py -v
python -m pytest tests/test_funnel_agent.py -v
...
```

### E2E 테스트

```bash
# 1주치 (297,357건) — 기준 테스트
curl -X POST http://localhost:8000/analysis/run \
  -d '{"domain_description": "GA4 e-commerce 패션/의류 쇼핑몰",
       "week_start": "20210115", "week_end": "20210121"}'

# 기대 결과:
# - status: done (2분 이내)
# - funnel/cohort/journey/performance: 정상 집계
# - anomaly: 베이스라인 부족 경고 (정상)
# - prediction: skipped (정상 — 데이터 부족)
# - ppt_url: /tmp/ppt_reports/*.pptx 존재
```

### 성능 기준

| 단계 | 현재 | 목표 |
|---|---|---|
| MongoDB 로드 | 수십 초 (blocking) | 각 에이전트 aggregation 1~3초 |
| 전체 파이프라인 | 2~3분 (로드만) | 2분 이내 (LLM 포함) |
| status 응답 | 로드 중 무응답 | 항상 즉시 응답 |

---

## 7. 현재 임시 상태 (작업 전 정리 필요)

`analysis.py`에 아래 코드가 남아있음 — 리팩토링 시작 전 제거:

```python
# 현재 analysis.py에 남아있는 임시 코드
def _bq_int64_to_int(v: dict) -> int: ...   # 제거 예정
def _make_param_value(v) -> dict: ...        # 제거 예정
def _prepare_doc(doc: dict) -> dict: ...     # 제거 예정

query["event_date"] = {...}
raw_docs = await events_col.find(query).to_list(length=500_000)  # 제거 예정
raw_logs = [_prepare_doc(doc) for doc in raw_docs]               # 제거 예정
```

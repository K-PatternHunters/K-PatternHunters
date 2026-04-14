# Cohort Analysis Agent

## 역할

첫 구매 발생 주차 기준으로 유저를 코호트로 분류하고,
코호트별 주차별 재구매율(retention)과 누적 revenue를 분석한다.
이탈이 주로 몇 주차에 집중되는지, 어느 코호트의 LTV가 높은지를 파악한다.

---

## Input (state에서 읽는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `week_start` | str | 분석 대상 주 시작일 |
| `week_end` | str | 분석 대상 주 종료일 |
| `field_mapping` | dict | Schema Mapping Agent 결과 |
| `context.cohort.definition` | str | 코호트 분류 기준 (e.g. `"first_purchase_week"`) |
| `context.cohort.metrics` | list[str] | 분석 지표 (e.g. `["retention_rate", "revenue_per_user"]`) |

## Output (state에 쓰는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `cohort_result` | dict | 코호트 분석 결과 전체 |

### cohort_result 구조

```python
{
    "cohort_definition": "first_purchase_week",
    "cohorts": [
        {
            "cohort_week": "2021-W01",        # 첫 구매 발생 주차
            "cohort_size": 320,               # 해당 주차 신규 구매자 수
            "weeks": [
                {
                    "week_offset": 0,         # 코호트 기준 주차 (0 = 첫 구매 주)
                    "retained_users": 320,
                    "retention_rate": 1.0,
                    "revenue": 48000.0,
                    "revenue_per_user": 150.0
                },
                {
                    "week_offset": 1,
                    "retained_users": 96,
                    "retention_rate": 0.30,
                    "revenue": 12000.0,
                    "revenue_per_user": 125.0
                },
                {
                    "week_offset": 2,
                    "retained_users": 51,
                    "retention_rate": 0.16,
                    "revenue": 5100.0,
                    "revenue_per_user": 100.0
                }
                # ... 분석 가능한 주차까지
            ]
        },
        {
            "cohort_week": "2021-W02",
            "cohort_size": 280,
            "weeks": [...]
        }
    ],
    "summary": {
        "avg_week1_retention": 0.28,         # 전체 코호트 평균 1주차 retention
        "best_retention_cohort": "2021-W03", # retention 가장 높은 코호트
        "typical_churn_week": 1,             # 이탈이 가장 많이 발생하는 주차 offset
        "new_buyer_trend": "increasing"      # 신규 구매자 수 추세 (increasing/decreasing/stable)
    }
}
```

---

## 분석 로직

### 1. 코호트 분류
- `user_pseudo_id` 기준으로 각 유저의 첫 `purchase` 이벤트 발생 주차 추출
- MongoDB aggregation: `purchase` 이벤트만 필터 → `user_pseudo_id` group → `min(event_date)` → 주차(ISO week) 변환

### 2. 주차별 retention 계산
- 각 코호트의 유저가 `week_offset` N주 후에 다시 `purchase` 이벤트를 발생시켰는지 확인
- `retained_users = 코호트 유저 중 해당 week_offset에 재구매한 유저 수`
- `retention_rate = retained_users / cohort_size`

### 3. 주차별 revenue 계산
- 각 코호트 유저가 해당 week_offset에 발생시킨 `purchase_revenue` 합산
- `revenue_per_user = revenue / cohort_size` (retained 기준 아닌 전체 코호트 기준)

### 4. 요약 지표 계산
- 전체 코호트 평균 1주차 retention
- 코호트별 1주차 retention 비교 → 최고 코호트 판별
- week_offset별 평균 drop-off → 이탈 집중 주차 판별
- 코호트 크기(`cohort_size`) 추세 → 신규 구매자 증감 파악

---

## 주요 고려사항

- 샘플 데이터셋 특성상 코호트 관찰 가능 기간이 제한적일 수 있음 → 가용 데이터 내에서만 분석
- 동일 유저가 여러 주차에 구매할 경우 첫 구매 주차만 코호트 기준으로 사용
- retention은 **재구매** 기준 (재방문이 아닌 재구매 이벤트 발생 여부)
- 볼륨 이슈: MongoDB aggregation pipeline으로 처리, raw document 메모리 로드 금지

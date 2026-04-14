# Performance Analysis Agent

## 역할

이번 주의 전반적인 KPI를 집계하고, 트래픽 소스/디바이스/상품 카테고리별 성과를 분석한다.
전주 대비 변화 방향을 파악하여 이번 주 퍼포먼스의 전체 요약을 생성한다.

---

## Input (state에서 읽는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `week_start` | str | 분석 대상 주 시작일 |
| `week_end` | str | 분석 대상 주 종료일 |
| `field_mapping` | dict | Schema Mapping Agent 결과 |
| `context.performance.kpis` | list[str] | 집계할 KPI 목록 |
| `context.performance.breakdowns` | list[str] | 세그먼트 breakdown 기준 |

## Output (state에 쓰는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `performance_result` | dict | 퍼포먼스 분석 결과 전체 |

### performance_result 구조

```python
{
    "period": {
        "week_start": "20210101",
        "week_end": "20210107"
    },
    "kpis": {
        "total_revenue": 125000.0,
        "transaction_count": 820,
        "arpu": 15.2,                    # average revenue per user (전체 유저 기준)
        "session_count": 12000,
        "conversion_rate": 0.068,        # transaction_count / session_count
        "bounce_rate": 0.42              # 단일 이벤트로 종료된 세션 비율
    },
    "daily_breakdown": [
        {
            "date": "20210101",
            "revenue": 17000.0,
            "transaction_count": 110,
            "session_count": 1600
        }
        # ... 7일치
    ],
    "by_traffic_source": [
        {
            "source": "google",
            "session_count": 5000,
            "transaction_count": 380,
            "revenue": 52000.0,
            "conversion_rate": 0.076
        }
        # ...
    ],
    "by_device_category": [
        {
            "device": "mobile",
            "session_count": 7200,
            "transaction_count": 380,
            "revenue": 54000.0,
            "conversion_rate": 0.053
        },
        {
            "device": "desktop",
            "session_count": 4200,
            "transaction_count": 380,
            "revenue": 62000.0,
            "conversion_rate": 0.090
        }
    ],
    "by_item_category": [
        {
            "category": "Apparel",
            "view_count": 8000,
            "add_to_cart_count": 2400,
            "purchase_count": 420,
            "revenue": 58000.0,
            "purchase_rate": 0.053        # purchase_count / view_count
        }
        # ...
    ],
    "wow_change": {
        # 전주 대비 변화율 (전주 데이터가 있는 경우에만)
        "total_revenue": +0.12,          # +12%
        "transaction_count": +0.08,
        "session_count": -0.03,
        "conversion_rate": +0.05
    }
}
```

---

## 분석 로직

### 1. 주간 KPI 집계
- `total_revenue`: `purchase` 이벤트의 `purchase_revenue` 합산
- `transaction_count`: `purchase` 이벤트 수 (중복 제거: `transaction_id` distinct)
- `arpu`: `total_revenue / distinct user_pseudo_id 수`
- `session_count`: `session_id` distinct 수
- `conversion_rate`: `transaction_count / session_count`
- `bounce_rate`: 이벤트가 1개뿐인 세션 수 / 전체 세션 수

### 2. 일별 breakdown
- `event_date` 기준으로 `revenue`, `transaction_count`, `session_count` 일별 집계

### 3. 트래픽 소스별 breakdown
- `traffic_source` 기준 group → KPI 집계
- `field_mapping`의 `traffic_source` 경로 참조

### 4. 디바이스별 breakdown
- `device_category` 기준 group → KPI 집계

### 5. 상품 카테고리별 breakdown
- `item_category` 기준 group
- `view_item`, `add_to_cart`, `purchase` 이벤트별 count + revenue 집계

### 6. 전주 대비 변화율 (WoW)
- `week_start` - 7일 ~ `week_end` - 7일 범위로 동일 집계 재실행
- `wow_change = (this_week - last_week) / last_week`
- 전주 데이터가 없으면 `wow_change: null`

---

## 주요 고려사항

- `transaction_id` distinct로 중복 구매 이벤트 방지
- WoW 계산을 위해 전주 데이터 추가 쿼리 필요 (별도 aggregation 1회)
- `by_item_category`는 items 배열 unwind → category group 순서로 처리
- 볼륨 이슈: 전부 MongoDB aggregation pipeline 처리

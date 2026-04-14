# Funnel Analysis Agent

## 역할

유저의 구매 퍼널 단계별 전환율과 이탈률을 분석한다.
어느 스텝에서 얼마나 이탈하는지, 어떤 세그먼트가 전환율이 높은지를 파악한다.

---

## Input (state에서 읽는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `week_start` | str | 분석 대상 주 시작일 |
| `week_end` | str | 분석 대상 주 종료일 |
| `field_mapping` | dict | Schema Mapping Agent 결과 |
| `context.funnel.steps` | list[str] | 분석할 퍼널 스텝 이벤트 목록 |
| `context.funnel.key_metric` | str | 핵심 지표 (e.g. `"conversion_rate"`) |

## Output (state에 쓰는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `funnel_result` | dict | 퍼널 분석 결과 전체 |

### funnel_result 구조

```python
{
    "steps": [
        {
            "event_name": "session_start",
            "user_count": 10000,
            "drop_off_rate": 0.0,        # 이전 스텝 대비 이탈율 (%)
            "conversion_rate": 1.0       # 첫 스텝 대비 누적 전환율
        },
        {
            "event_name": "view_item",
            "user_count": 7000,
            "drop_off_rate": 30.0,
            "conversion_rate": 0.70
        },
        {
            "event_name": "add_to_cart",
            "user_count": 3000,
            "drop_off_rate": 57.1,
            "conversion_rate": 0.30
        },
        {
            "event_name": "begin_checkout",
            "user_count": 1500,
            "drop_off_rate": 50.0,
            "conversion_rate": 0.15
        },
        {
            "event_name": "purchase",
            "user_count": 800,
            "drop_off_rate": 46.7,
            "conversion_rate": 0.08
        }
    ],
    "overall_conversion_rate": 0.08,     # 첫 스텝 → 마지막 스텝
    "biggest_drop_off_step": "view_item → add_to_cart",
    "breakdowns": {
        "device_category": {
            "mobile": {"overall_conversion_rate": 0.05, "steps": [...]},
            "desktop": {"overall_conversion_rate": 0.12, "steps": [...]}
        },
        "traffic_source": {
            "google": {"overall_conversion_rate": 0.09, "steps": [...]},
            "direct": {"overall_conversion_rate": 0.11, "steps": [...]}
        }
    }
}
```

---

## 분석 로직

### 1. 퍼널 스텝별 유저 수 집계
- `context.funnel.steps`에 정의된 이벤트 순서대로 집계
- 기준: `user_pseudo_id` (동일 유저가 해당 이벤트를 week 내에 발생시켰는지)
- MongoDB aggregation: `event_date` range 필터 → `event_name` 기준 group

### 2. drop-off / conversion rate 계산
- `drop_off_rate = (prev_step_users - curr_step_users) / prev_step_users * 100`
- `conversion_rate = curr_step_users / first_step_users`

### 3. 세그먼트별 breakdown
- `device_category`, `traffic_source` 기준으로 동일 로직 반복
- `field_mapping`에서 해당 필드 경로 참조

### 4. 최대 이탈 스텝 판별
- drop_off_rate 가장 높은 구간 → `biggest_drop_off_step`

---

## 주요 고려사항

- 유저는 week 내 여러 세션에 걸쳐 퍼널을 완료할 수 있음 → 세션 단위가 아닌 **유저 단위** 집계
- 퍼널 스텝은 순서를 강제하지 않음 (해당 이벤트 발생 여부만 확인)
- 볼륨 이슈: MongoDB aggregation pipeline으로 처리, raw document 메모리 로드 금지

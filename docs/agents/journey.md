# Journey & Flow Analysis Agent

## 역할

세션 내 이벤트 시퀀스를 추출하여 유저 행동 경로를 분석한다.
구매로 이어진 경로와 이탈로 끝난 경로의 패턴을 비교하고,
이벤트 간 전이 확률(transition matrix)을 계산한다.

---

## Input (state에서 읽는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `week_start` | str | 분석 대상 주 시작일 |
| `week_end` | str | 분석 대상 주 종료일 |
| `field_mapping` | dict | Schema Mapping Agent 결과 |
| `context.journey.top_n_paths` | int | 상위 N개 경로 추출 (e.g. `10`) |
| `context.journey.max_depth` | int | 경로 최대 이벤트 수 (e.g. `5`) |
| `context.journey.entry_events` | list[str] | 경로 시작 이벤트 (e.g. `["session_start"]`) |
| `context.journey.exit_events` | list[str] | 경로 종료 이벤트 (e.g. `["purchase", "session_end"]`) |

## Output (state에 쓰는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `journey_result` | dict | 여정 분석 결과 전체 |

### journey_result 구조

```python
{
    "converted_paths": [
        {
            "path": ["session_start", "view_item", "add_to_cart", "begin_checkout", "purchase"],
            "session_count": 420,
            "ratio": 0.18       # 전체 구매 세션 중 이 경로 비율
        },
        {
            "path": ["session_start", "view_item", "view_item", "add_to_cart", "purchase"],
            "session_count": 210,
            "ratio": 0.09
        }
        # top_n_paths 개
    ],
    "churned_paths": [
        {
            "path": ["session_start", "view_item", "session_end"],
            "session_count": 1800,
            "ratio": 0.22       # 전체 이탈 세션 중 이 경로 비율
        }
        # top_n_paths 개
    ],
    "transition_matrix": {
        # 이벤트 A → 이벤트 B 전이 확률
        "session_start": {
            "view_item": 0.72,
            "session_end": 0.20,
            "page_view": 0.08
        },
        "view_item": {
            "add_to_cart": 0.35,
            "view_item": 0.30,
            "session_end": 0.25,
            "begin_checkout": 0.10
        },
        "add_to_cart": {
            "begin_checkout": 0.55,
            "view_item": 0.30,
            "session_end": 0.15
        }
        # ...
    },
    "summary": {
        "total_sessions": 12000,
        "converted_sessions": 800,
        "churned_sessions": 11200,
        "most_common_converted_path": ["session_start", "view_item", "add_to_cart", "begin_checkout", "purchase"],
        "pre_churn_pattern": "view_item → session_end"   # 이탈 직전 가장 많이 발생하는 패턴
    }
}
```

---

## 분석 로직

### 1. 세션별 이벤트 시퀀스 추출
- `session_id` 기준으로 이벤트를 `event_timestamp` 순 정렬하여 시퀀스 구성
- `max_depth`까지만 사용 (이후 이벤트 truncate)
- MongoDB aggregation: session_id group → `event_name` 배열로 push → sort by timestamp

### 2. 전환/이탈 세션 분류
- 세션 내 `exit_events` 중 `purchase`가 포함되면 → converted session
- 그 외 `session_end` 등으로 종료되면 → churned session

### 3. 상위 N개 경로 추출
- converted / churned 각각에서 동일한 path 시퀀스를 group → count
- 상위 `top_n_paths`개 추출 → `ratio` 계산

### 4. Transition Matrix 계산
- 전체 세션의 연속된 이벤트 쌍 (A → B) 추출
- 이벤트 A 다음에 각 이벤트 B가 나타나는 비율 계산
- `P(B|A) = count(A→B) / count(A→*)`

### 5. Pre-churn 패턴 판별
- churned_paths에서 마지막 두 이벤트 쌍(종료 직전) 집계
- 가장 많이 나타나는 패턴 → `pre_churn_pattern`

---

## 주요 고려사항

- `max_depth` 제한으로 긴 세션도 안전하게 처리
- 동일 이벤트 반복(e.g. `view_item → view_item`) 허용 — 실제 유저 행동 반영
- Transition Matrix는 상위 N개 노드만 포함 (노드 수 폭발 방지)
- 볼륨 이슈: 세션 시퀀스 구성을 MongoDB aggregation 내에서 처리, Python 레벨에서 전체 raw 로드 금지

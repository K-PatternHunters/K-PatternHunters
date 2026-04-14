# Schema Mapping Agent

## 역할

MongoDB `raw_logs` collection의 GA4 원본 nested 스키마를 분석하여,
다운스트림 분석 agent들이 공통으로 사용할 **normalized field mapping table**을 생성한다.

각 분석 agent는 raw 필드명을 직접 다루지 않고, 이 mapping table을 참조한다.

---

## Input (state에서 읽는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `week_start` | str | 분석 대상 주 시작일 |
| `week_end` | str | 분석 대상 주 종료일 |
| `domain` | str | 도메인 카테고리 |

## Output (state에 쓰는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `field_mapping` | dict | raw field path → normalized field name 매핑 테이블 |

### field_mapping 구조 예시

```python
{
    # 이벤트 기본 필드
    "event_date": "event_date",
    "event_name": "event_name",
    "event_timestamp": "event_timestamp",
    "user_pseudo_id": "user_pseudo_id",

    # event_params 배열에서 추출 (key 기준)
    "event_params[key=session_id].value.int_value": "session_id",
    "event_params[key=page_location].value.string_value": "page_location",
    "event_params[key=source].value.string_value": "traffic_source",
    "event_params[key=medium].value.string_value": "traffic_medium",
    "event_params[key=value].value.float_value": "event_value",
    "event_params[key=engagement_time_msec].value.int_value": "engagement_time_msec",

    # ecommerce 필드
    "ecommerce.transaction_id": "transaction_id",
    "ecommerce.purchase_revenue": "purchase_revenue",
    "ecommerce.tax": "tax",
    "ecommerce.shipping": "shipping",

    # items 배열 (첫 번째 item 기준 또는 집계)
    "items[].item_id": "item_id",
    "items[].item_name": "item_name",
    "items[].item_category": "item_category",
    "items[].price": "item_price",
    "items[].quantity": "item_quantity",

    # device / geo
    "device.category": "device_category",
    "device.mobile_brand_name": "device_brand",
    "geo.country": "geo_country",
    "geo.city": "geo_city",

    # traffic source (top-level)
    "traffic_source.source": "traffic_source",
    "traffic_source.medium": "traffic_medium",
    "traffic_source.name": "traffic_campaign",
}
```

---

## 처리 로직

### 1. 샘플 document 추출
- `raw_logs` collection에서 해당 week 데이터 중 100개 샘플 추출 (집계 부하 최소화)
- nested 필드 구조 파악 (`event_params`, `ecommerce`, `items`, `device`, `geo`)

### 2. 표준 GA4 스펙과 비교
- 알려진 GA4 BigQuery export 스키마와 실제 document 구조 비교
- 필드명/타입이 표준과 일치하면 직접 매핑

### 3. LLM 추론 (불일치 시)
- 표준 스펙과 다른 필드가 발견된 경우에만 LLM 호출
- LLM에게 필드명과 샘플 값을 제공하여 의미 추론
- 예: 커스텀 `event_params` key가 있는 경우

### 4. event_params 처리 전략
- `event_params` 전체를 flatten하지 않음 (볼륨 이슈)
- 각 분석 agent가 필요한 key를 `field_mapping`에서 조회하여 MongoDB aggregation pipeline 내에서 직접 추출
- `field_mapping`은 "어떻게 뽑을지"에 대한 경로 정보를 담음

---

## 다운스트림 사용 방식

분석 agent들은 `state["field_mapping"]`을 참조하여 MongoDB aggregation을 구성한다.

```python
# 예: funnel_agent에서 사용
fm = state["field_mapping"]
# "event_params[key=session_id].value.int_value" → "$event_params"에서 filter+project
session_id_path = fm["session_id"]  # agent가 path 해석하여 aggregation에 사용
```

---

## 주요 고려사항

- **LLM 호출은 최소화**: 표준 GA4 스펙과 다른 필드가 있을 때만 호출
- **볼륨 안전**: 샘플 100개만 읽어 스키마 파악, raw document 전체 로드 금지
- **멱등성**: 동일 week에 대해 재실행해도 동일한 mapping 결과

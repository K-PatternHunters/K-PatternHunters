# Anomaly Detection Agent

## 역할

일별 핵심 지표에서 통계적 이상값을 탐지하고, LLM이 각 이상값을 해석한다.
탐지는 Z-score 기반 deterministic 방식, 해석은 LLM 호출.

---

## Input (state에서 읽는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `week_start` | str | 분석 대상 주 시작일 |
| `week_end` | str | 분석 대상 주 종료일 |
| `field_mapping` | dict | Schema Mapping Agent 결과 |
| `context.anomaly.target_metrics` | list[str] | 탐지 대상 지표 |
| `context.anomaly.method` | str | 탐지 방식 (e.g. `"zscore"`) |
| `context.anomaly.threshold` | float | 이상값 판정 기준 Z-score (e.g. `2.0`) |

## Output (state에 쓰는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `anomaly_result` | dict | 이상 탐지 결과 전체 |

### anomaly_result 구조

```python
{
    "method": "zscore",
    "threshold": 2.0,
    "lookback_weeks": 4,        # 평균/표준편차 계산에 사용한 과거 주 수
    "anomalies": [
        {
            "metric": "daily_revenue",
            "date": "20210104",
            "observed_value": 32000.0,
            "expected_mean": 17800.0,
            "expected_std": 2100.0,
            "z_score": 6.76,
            "direction": "high",         # "high" or "low"
            "llm_interpretation": "1월 4일 매출이 평균 대비 6.76 sigma 급증했습니다. 해당 날짜는 월요일로, 주말 대비 트래픽 집중 또는 프로모션 효과로 인한 이상치일 가능성이 높습니다."
        },
        {
            "metric": "daily_conversion_rate",
            "date": "20210106",
            "observed_value": 0.021,
            "expected_mean": 0.068,
            "expected_std": 0.008,
            "z_score": -5.88,
            "direction": "low",
            "llm_interpretation": "1월 6일 전환율이 평균 대비 급락했습니다. 세션 수는 정상이나 구매가 발생하지 않아 결제 시스템 오류 또는 특정 트래픽 소스의 품질 저하를 의심할 수 있습니다."
        }
    ],
    "clean_metrics": [
        # 이상값 없는 지표 목록
        {
            "metric": "daily_session_count",
            "max_z_score": 1.23,
            "status": "normal"
        }
    ],
    "summary": {
        "total_anomalies": 2,
        "affected_metrics": ["daily_revenue", "daily_conversion_rate"],
        "most_abnormal_date": "20210104"
    }
}
```

---

## 분석 로직

### 1. 과거 데이터 수집 (baseline 구축)
- 현재 week 이전 4주치 일별 지표 집계 (lookback_weeks = 4)
- 각 지표별 28개 일별 값 → `mean`, `std` 계산

### 2. 이번 주 일별 지표 집계
- `target_metrics`에 정의된 지표를 일별로 집계
  - `daily_revenue`: 일별 `purchase_revenue` 합산
  - `daily_session_count`: 일별 `session_id` distinct 수
  - `daily_conversion_rate`: 일별 `transaction_count / session_count`

### 3. Z-score 계산 및 이상값 판정
- `z_score = (observed - mean) / std`
- `|z_score| >= threshold` → 이상값으로 판정
- `std == 0`인 경우 해당 지표 skip

### 4. LLM 해석
- 이상값이 탐지된 경우에만 LLM 호출
- LLM에게 전달하는 정보:
  - 지표명, 날짜, 관측값, 기대값(mean), z_score, direction
  - 도메인 컨텍스트 (e.g. "ecommerce")
  - 해당 날짜의 요일 정보
- LLM output: 이상값의 가능한 원인 및 의미를 1~2문장으로 해석

---

## 주요 고려사항

- **LLM 호출 최소화**: 이상값이 없으면 LLM 미호출
- **std = 0 처리**: 과거 4주 데이터가 모두 동일한 값이면 해당 지표 skip
- **lookback 데이터 부족**: 4주치 미만이면 가용 데이터로만 baseline 구성 (최소 7일)
- 볼륨 이슈: 일별 집계는 MongoDB aggregation pipeline 처리
- Z-score 기준이므로 정규분포 가정 — 샘플 데이터셋 특성상 적합한 방식

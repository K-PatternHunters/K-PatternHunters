# Prediction Agent

## 역할

직전 N주 weekly 데이터를 기반으로 다음 주 핵심 지표를 예측한다.
복잡한 ML 모델 없이 linear trend 기반의 경량 예측을 제공하며,
LLM이 예측 결과와 추세 방향을 코멘트한다.

---

## Input (state에서 읽는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `week_start` | str | 분석 대상 주 시작일 |
| `week_end` | str | 분석 대상 주 종료일 |
| `field_mapping` | dict | Schema Mapping Agent 결과 |
| `context.prediction.targets` | list[str] | 예측 대상 지표 |
| `context.prediction.method` | str | 예측 방식 (e.g. `"linear_trend"`) |
| `context.prediction.lookback_weeks` | int | 학습에 사용할 과거 주 수 (e.g. `4`) |

## Output (state에 쓰는 값)

| 키 | 타입 | 설명 |
|----|------|------|
| `prediction_result` | dict | 예측 결과 전체 |

### prediction_result 구조

```python
{
    "method": "linear_trend",
    "lookback_weeks": 4,
    "predictions": [
        {
            "target": "next_week_revenue",
            "historical": [
                {"week": "2020-W49", "value": 108000.0},
                {"week": "2020-W50", "value": 115000.0},
                {"week": "2020-W51", "value": 119000.0},
                {"week": "2020-W52", "value": 125000.0}   # 현재 주
            ],
            "predicted_value": 131200.0,
            "confidence_interval": {
                "lower": 118000.0,
                "upper": 144400.0
            },
            "trend_direction": "increasing",     # "increasing" / "decreasing" / "stable"
            "trend_slope": 5733.3,               # 주당 증가량
            "llm_comment": "최근 4주 매출이 꾸준히 증가하는 추세입니다. 다음 주 예측 매출은 약 131,200원으로, 현재 주 대비 약 5% 성장이 기대됩니다. 단, 연휴 또는 계절적 요인이 있을 경우 실제 값은 신뢰 구간 밖으로 벗어날 수 있습니다."
        },
        {
            "target": "next_week_transaction_count",
            "historical": [
                {"week": "2020-W49", "value": 710},
                {"week": "2020-W50", "value": 755},
                {"week": "2020-W51", "value": 790},
                {"week": "2020-W52", "value": 820}
            ],
            "predicted_value": 852,
            "confidence_interval": {
                "lower": 790,
                "upper": 914
            },
            "trend_direction": "increasing",
            "trend_slope": 36.7,
            "llm_comment": "거래 건수도 매주 꾸준히 증가하고 있습니다. 다음 주 예측 거래 수는 약 852건으로, 현재 추세가 유지된다면 달성 가능한 수준입니다."
        }
    ],
    "summary": {
        "overall_trend": "increasing",
        "data_quality_warning": null    # 데이터 부족 시 경고 메시지
    }
}
```

---

## 분석 로직

### 1. 과거 주간 데이터 수집
- `week_start` 기준으로 직전 `lookback_weeks`개 주(week) 데이터 집계
- 각 target별 주간 합산값 추출
  - `next_week_revenue`: 주간 `purchase_revenue` 합산
  - `next_week_transaction_count`: 주간 `transaction_id` distinct 수

### 2. Linear Trend 예측
- `x = [0, 1, 2, ..., lookback_weeks-1]`, `y = 과거 주간 값` 으로 최소제곱법(least squares) 적합
- `slope`, `intercept` 계산
- `predicted_value = slope * lookback_weeks + intercept` (다음 주 예측)

### 3. 신뢰 구간 계산
- 잔차(residuals) 표준편차 기반 ±1.96σ 구간
- `lower = predicted - 1.96 * residual_std`
- `upper = predicted + 1.96 * residual_std`

### 4. 추세 방향 판별
- `slope > 0` + 통계적으로 유의미 → `"increasing"`
- `slope < 0` + 통계적으로 유의미 → `"decreasing"`
- 그 외 → `"stable"`
- 유의미 기준: `|slope| > 0.05 * mean(historical_values)`

### 5. LLM 코멘트
- 예측값, 추세 방향, 신뢰 구간, 도메인 컨텍스트를 LLM에 전달
- LLM output: 예측 해석 + 주의사항 1~2문장

---

## 주요 고려사항

- **데이터 부족**: lookback_weeks 미만 데이터 존재 시 가용 데이터만 사용, `data_quality_warning` 기록
- **최소 데이터 요건**: 최소 2주치 데이터 필요. 1주치 이하면 해당 target skip
- **음수 예측값 처리**: 예측값이 음수로 나오면 0으로 클리핑
- 볼륨 이슈: 주간 집계는 MongoDB aggregation pipeline 처리
- 예측 모델은 경량(numpy 또는 순수 Python 최소제곱법) — scikit-learn 등 외부 ML 라이브러리 불필요

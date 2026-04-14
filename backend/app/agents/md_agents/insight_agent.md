# insight_agent — 개발 노트

## 역할

6개 분석 에이전트(funnel, cohort, journey, performance, anomaly, prediction)의 출력을
종합해 **비즈니스 인사이트를 도출**하고, ppt_agent가 슬라이드를 바로 렌더링할 수 있는
**슬라이드 단위 구조화 리포트(`InsightReport`)**를 생성하는 에이전트.

---

## 핵심 설계 결정

### 출력 포맷: 슬라이드 단위 구조화 (`InsightReport` + `SlideContent`)

| 후보 방식 | 장점 | 단점 | 결론 |
|---|---|---|---|
| 자유 형식 텍스트 (마크다운) | 생성 유연성 | ppt_agent가 다시 파싱해야 함, 오류 위험 | ❌ |
| 분석별 요약 dict | 단순함 | 슬라이드 구조와 1:1 매핑 안됨 | ❌ |
| **슬라이드 단위 Pydantic 모델** | ppt_agent가 파싱 없이 직접 렌더링 가능, 명확한 계약 | 초기 설계 비용 | **✅ 채택** |

**`SlideContent` 단위로 구조화한 이유:**
- ppt_agent가 `slide_order`를 순회하며 각 슬라이드를 바로 생성 가능
- `chart_type`으로 적절한 시각화 선택 가능 (funnel_chart, heatmap, sankey 등)
- `chart_data_key`로 원본 metrics 데이터를 직접 참조 가능
- `metrics` 필드에 핵심 수치를 미리 추출해 강조 박스/카드에 바로 사용 가능

---

## 모델 구조

### `SlideContent` (슬라이드 1장)

```
SlideContent
├── slide_type      : str           # 슬라이드 종류 (funnel, cohort 등)
├── title           : str           # 슬라이드 제목
├── headline        : str           # 핵심 메시지 1문장 (서브타이틀 또는 콜아웃)
├── bullets         : list[str]     # 세부 발견사항 (3-5개)
├── metrics         : dict[str,Any] # 강조 표시할 핵심 수치
├── chart_type      : str           # 권장 차트 유형
├── chart_data_key  : str           # PipelineState에서 원본 데이터 참조 키
└── speaker_notes   : str           # 발표자 노트 (슬라이드 미표시)
```

### `InsightReport` (전체 리포트)

```
InsightReport
│
│  [메타]
├── domain                  : str
├── analysis_period         : str
├── overall_sentiment       : "positive"|"negative"|"neutral"|"mixed"
│
│  [임원 요약층]
├── executive_summary       : str              # 3-5문장 전체 요약
├── top_findings            : list[str]        # 비즈니스 임팩트 순 Top 3-5 발견사항
├── recommendations         : list[str]        # 구체적 행동 권고 Top 3-5
│
│  [슬라이드별 컨텐츠]
├── performance_slide       : SlideContent | None
├── funnel_slide            : SlideContent | None
├── cohort_slide            : SlideContent | None
├── journey_slide           : SlideContent | None
├── anomaly_slide           : SlideContent | None
├── prediction_slide        : SlideContent | None
│
│  [교차 분석]
├── cross_analysis_findings : list[str]        # 복수 분석 결합 시 나오는 인사이트
│
│  [PPT 조립 힌트]
└── slide_order             : list[str]        # ppt_agent용 슬라이드 순서
```

---

## chart_type 기준

| 슬라이드 | 권장 chart_type |
|---|---|
| performance | `kpi_cards` + `bar_chart` |
| funnel | `funnel_chart` |
| cohort | `heatmap` |
| journey | `sankey` 또는 `table` |
| anomaly | `line_chart` (이상 포인트 어노테이션) |
| prediction | `line_chart` (실적 + 예측선) |

---

## 처리 흐름

```
state["domain_context"]
state["performance_metrics"]   ┐
state["funnel_metrics"]        │
state["cohort_metrics"]        ├── 가용한 것만 사용 (None이면 해당 슬라이드 = null)
state["journey_metrics"]       │
state["anomaly_metrics"]       │
state["prediction_metrics"]    ┘
        │
        ▼
  _build_human_message()
  (도메인 컨텍스트 + 분석 결과 직렬화, 각 3000자 상한)
        │
        ▼
  ChatOpenAI(gpt-4o, temperature=0.2)
  .with_structured_output(InsightReport)
        │
        ▼
  InsightReport.model_dump()
        │
        ▼
  state["insight_report"]  →  ppt_agent로 전달
```

### gpt-4o / temperature=0.2 선택 이유
- context_agent(gpt-4o-mini, temp=0): 도메인 설정 생성 → 정확성 우선
- insight_agent(gpt-4o, temp=0.2): 복수 분석 종합 + 내러티브 생성 → 추론력 + 약간의 유연성 필요

---

## 강건성 처리

- 분석 에이전트 미실행 시 해당 `*_slide` 필드를 `null`로 설정 (오류 없이 통과)
- 모든 서브 에이전트 결과가 없어도 도메인 컨텍스트만으로 리포트 생성 가능 (경고 로그 출력)
- 각 분석 결과는 3000자로 잘라 프롬프트 길이 제어

---

## 트러블슈팅

### `openai.BadRequestError: Invalid schema for response_format` (테스트 실패)
- **원인**: `context_agent`와 동일. `InsightReport` 내 `SlideContent.metrics: dict[str, Any]` 필드가
  OpenAI strict mode의 `additionalProperties: false` 조건을 만족시키지 못해 400 에러 발생.
- **해결**: `.with_structured_output(InsightReport, method="function_calling")`으로 변경.

### `SlideContent` 미사용 import 경고
- **원인**: `insight_agent.py`에서 `SlideContent`를 import했으나, `InsightReport` 내부에서만 참조됨
- **해결**: `insight_agent.py`의 import에서 `SlideContent` 제거 완료

### `langchain_core`, `langchain_openai` import 확인 불가 경고
- **원인**: VSCode Python 인터프리터가 `.venv`를 바라보지 않음 (context_agent와 동일 문제)
- **해결**: `Cmd+Shift+P` → `Python: Select Interpreter` → `backend/.venv/bin/python` 선택

---

## 미구현 의존성 (향후 작업)

| 항목 | 현재 상태 | 영향 |
|---|---|---|
| 모든 분석 에이전트 | `NotImplementedError` | `*_metrics` 키 없음 → 슬라이드 null, 경고 로그 |
| `config.get_settings()` | OPENAI_API_KEY placeholder | 실제 키 주입 필요 |

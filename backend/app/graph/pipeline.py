"""Defines and compiles the LangGraph StateGraph that orchestrates the full analysis pipeline.

Graph topology (고정 순서):

    [START]
       │
    context_agent          ← 항상 고정: 도메인 컨텍스트 생성 (LLM + RAG + 웹검색)
       │
    schema_mapping_agent   ← 항상 고정: GA4 필드 → 정규화 필드명 매핑
       │
    analysis_dispatcher    ← 병렬 실행: domain_context.recommended_sub_agents 기반
       │  (funnel / cohort / journey / performance / anomaly / prediction 중 선택)
       │
    insight_agent          ← 항상 고정: 분석 결과 종합 → InsightReport (LLM)
       │
    ppt_agent              ← 항상 고정: InsightReport → PowerPoint 생성
       │
    [END]

─────────────────────────────────────────────────────────────────
State 전달 전략
─────────────────────────────────────────────────────────────────

1. As-is 전달 (원본 구조/값 그대로 유지)
   - raw_logs        : 분석 에이전트 전체가 원본 이벤트 로그를 직접 순회
   - domain_context  : 에이전트별 config (funnel_config.steps 등) 그대로 참조
   - field_mapping   : 정규화 필드명 매핑 — 분석 에이전트가 정확한 키를 필요로 함
   - insight_report  : SlideContent 구조 — ppt_agent가 렌더링 시 변형 없이 소비

2. 요약 처리 (LLM 컨텍스트 윈도우 관리)
   - *_metrics       : state에는 원본 전체를 보존
                       insight_agent 내부의 _compact(data, max_chars=3000)가
                       LLM 프롬프트 구성 시 섹션당 3000자로 잘라 전달
                       → 원본은 손상되지 않으면서 LLM 비용·오류 방지

3. chart_data_key 간접 참조 (PPT 차트 데이터)
   - SlideContent.chart_data_key 에 "funnel_metrics" 등 state 키 이름을 저장
   - ppt_agent는 state[chart_data_key] 로 원본 수치 데이터를 직접 가져와 차트 렌더링
   - insight_agent는 해석/스토리텔링, ppt_agent는 원본 수치 — 역할 분리
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.anomaly_agent import anomaly_agent
from app.agents.cohort_agent import cohort_agent
from app.agents.context_agent import context_agent
from app.agents.funnel_agent import funnel_agent
from app.agents.insight_agent import insight_agent
from app.agents.journey_agent import journey_agent
from app.agents.performance_agent import performance_agent
from app.agents.prediction_agent import prediction_agent
from app.agents.ppt_agent import ppt_agent
from app.agents.schema_mapping_agent import schema_mapping_agent
from app.core.models import PipelineState

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Analysis agent registry
# ──────────────────────────────────────────────────────────────────────────────

_ANALYSIS_AGENTS: dict[str, Any] = {
    "funnel":      funnel_agent,
    "cohort":      cohort_agent,
    "journey":     journey_agent,
    "performance": performance_agent,
    "anomaly":     anomaly_agent,
    "prediction":  prediction_agent,
}


# ──────────────────────────────────────────────────────────────────────────────
# Parallel dispatcher node
# ──────────────────────────────────────────────────────────────────────────────

async def analysis_dispatcher(state: dict) -> dict:
    """LangGraph node: run recommended analysis agents in parallel.

    context_agent가 domain_context.recommended_sub_agents 에 실행할 에이전트 목록을
    결정해 두었으므로, 이 노드는 해당 목록을 읽어 asyncio.gather 로 병렬 실행한다.

    - 유효하지 않은 이름은 무시 (경고 로그)
    - 목록이 비어 있으면 전체 6개 실행 (폴백)
    - 개별 에이전트 예외는 격리 처리 — 하나가 실패해도 나머지 결과는 state에 반영
    """
    domain_context: dict = state.get("domain_context", {})
    recommended: list[str] = domain_context.get(
        "recommended_sub_agents", list(_ANALYSIS_AGENTS.keys())
    )

    valid: list[str] = [name for name in recommended if name in _ANALYSIS_AGENTS]
    if not valid:
        logger.warning(
            "analysis_dispatcher: recommended_sub_agents=%r 에 유효한 에이전트 없음 "
            "— 전체 실행으로 폴백",
            recommended,
        )
        valid = list(_ANALYSIS_AGENTS.keys())

    logger.info("analysis_dispatcher: 병렬 실행 에이전트=%s", valid)

    results = await asyncio.gather(
        *[_ANALYSIS_AGENTS[name](state) for name in valid],
        return_exceptions=True,
    )

    merged: dict = {}
    for name, result in zip(valid, results):
        if isinstance(result, BaseException):
            logger.error(
                "analysis_dispatcher: %s 실패 — %s",
                name,
                result,
                exc_info=result,
            )
        else:
            merged.update(result)

    return merged


# ──────────────────────────────────────────────────────────────────────────────
# Graph definition
# ──────────────────────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    builder = StateGraph(PipelineState)

    # 노드 등록
    builder.add_node("context_agent",        context_agent)
    builder.add_node("schema_mapping_agent", schema_mapping_agent)
    builder.add_node("analysis_dispatcher",  analysis_dispatcher)
    builder.add_node("insight_agent",        insight_agent)
    builder.add_node("ppt_agent",            ppt_agent)

    # 고정 순서 엣지
    builder.add_edge(START,                  "context_agent")
    builder.add_edge("context_agent",        "schema_mapping_agent")
    builder.add_edge("schema_mapping_agent", "analysis_dispatcher")
    builder.add_edge("analysis_dispatcher",  "insight_agent")
    builder.add_edge("insight_agent",        "ppt_agent")
    builder.add_edge("ppt_agent",            END)

    return builder


analysis_graph = _build_graph().compile()

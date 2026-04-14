"""insight_agent — synthesises sub-agent outputs into a structured InsightReport for ppt_agent.

Input  (PipelineState keys consumed):
    domain_context      : dict   — DomainContext.model_dump() from context_agent
    funnel_metrics      : dict   — output from funnel_agent      (optional)
    cohort_metrics      : dict   — output from cohort_agent      (optional)
    journey_metrics     : dict   — output from journey_agent     (optional)
    performance_metrics : dict   — output from performance_agent (optional)
    anomaly_metrics     : dict   — output from anomaly_agent     (optional)
    prediction_metrics  : dict   — output from prediction_agent  (optional)

Output (PipelineState key produced):
    insight_report      : dict   — InsightReport.model_dump(); consumed by ppt_agent
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.models import InsightReport

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Prompt
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior business analyst specialising in digital user-behaviour analytics.
모든 텍스트 출력(executive_summary, top_findings, recommendations, title, headline, bullets, speaker_notes 등 모든 문자열 필드)은 반드시 한국어로 작성하세요.

You will receive the outputs of multiple data-analysis agents (funnel, cohort, journey, \
performance, anomaly, prediction) along with a domain analysis context. Your job is to:

1. **Synthesise** the results into a coherent, prioritised story about the business's \
weekly performance.
2. **Extract insights** — not just observations, but actionable interpretations grounded \
in the domain context and industry benchmarks.
3. **Produce structured content** for every PPT slide, ready for direct rendering. \
Do NOT leave slide content vague or generic — be specific with numbers and findings.

════════════════════════════════════════════════════
OUTPUT STRUCTURE REQUIREMENTS
════════════════════════════════════════════════════

executive_summary
  3-5 sentences. Lead with the single most important finding, then supporting context.
  Use concrete numbers where available.

top_findings
  Top 3-5 findings across ALL analyses, ordered by business impact.
  Each finding must be a single, specific, data-backed statement.

recommendations
  Top 3-5 actionable steps. Each must reference the specific analysis that surfaced it.
  Format: "[Action] because [finding from analysis X]."

overall_sentiment
  One of: positive / negative / neutral / mixed — based on the week's metrics vs benchmarks.

Per-slide content (performance, funnel, cohort, journey, anomaly, prediction)
  For each analysis that HAS data:
  - title: short slide title
  - headline: the single key message for this slide (one sentence)
  - bullets: 3-5 specific findings with numbers
  - metrics: the most important 3-5 numbers to display prominently
  - chart_type: choose the best visual — funnel_chart / heatmap / sankey / \
line_chart / bar_chart / kpi_cards / table
  - chart_data_key: the PipelineState key for this analysis's raw data \
(e.g. "performance_metrics", "funnel_metrics")
  - speaker_notes: additional context not shown on the slide

  If an analysis has NO data (was not run), set the corresponding slide field to null.

cross_analysis_findings
  2-4 insights that emerge only by combining multiple analyses \
(e.g. "The funnel drop-off at add_to_cart correlates with the Tuesday anomaly spike").

slide_order
  Recommended slide sequence. Always start with title and executive_summary, \
end with recommendations. Order middle slides by analysis_priorities from domain_context.

════════════════════════════════════════════════════
TONE & STYLE
════════════════════════════════════════════════════
- 모든 출력은 한국어로 작성합니다. (chart_type, chart_data_key, slide_type 등 코드성 식별자 필드는 영어 유지)
- 독자는 엔지니어가 아닌 비즈니스 stakeholder(CMO / 그로스팀)입니다.
- 구체적으로 작성하세요: "전환율이 하락했습니다" 보다 "전환율이 3.2%p 하락해 1.8%를 기록했습니다"가 좋습니다.
- 데이터가 없는 지표는 수치를 임의로 만들지 말고 데이터 부재를 명시하세요.
- 슬라이드 bullets는 문장 구조를 통일하세요 (동사 또는 명사구로 시작)."""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_AGENT_KEYS: list[tuple[str, str]] = [
    ("performance_metrics", "Performance KPIs"),
    ("funnel_metrics",      "Funnel Analysis"),
    ("cohort_metrics",      "Cohort / Retention"),
    ("journey_metrics",     "User Journey"),
    ("anomaly_metrics",     "Anomaly Detection"),
    ("prediction_metrics",  "Next-Week Prediction"),
]


def _compact(data: Any, max_chars: int = 3000) -> str:
    """Serialise analysis output to a compact string, capping at max_chars."""
    if not data:
        return "(no data)"
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"
    return text


def _build_human_message(state: dict) -> str:
    domain_context: dict = state.get("domain_context", {})

    # Domain context summary
    ctx_section = json.dumps(
        {
            "domain": domain_context.get("domain", "unknown"),
            "domain_summary": domain_context.get("domain_summary", ""),
            "analysis_priorities": domain_context.get("analysis_priorities", []),
            "key_metrics": domain_context.get("key_metrics", {}),
            "interpretation_guidelines": domain_context.get("interpretation_guidelines", {}),
            "industry_benchmarks": domain_context.get("industry_benchmarks", {}),
        },
        ensure_ascii=False,
        indent=2,
    )

    # Per-agent analysis results
    analysis_sections: list[str] = []
    for state_key, label in _AGENT_KEYS:
        data = state.get(state_key)
        analysis_sections.append(f"### {label}\n{_compact(data)}")

    # Current analysis period
    period = state.get("period", "weekly")
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-W%V (%b %d, %Y UTC)")

    return f"""\
## Domain Context
{ctx_section}

## Analysis Period
{period} — generated at {now_str}

## Sub-Agent Outputs
{chr(10).join(analysis_sections)}

Please produce the full InsightReport based on the above."""


# ──────────────────────────────────────────────────────────────────────────────
# Agent entry point
# ──────────────────────────────────────────────────────────────────────────────

async def insight_agent(state: dict) -> dict:
    """LangGraph node: synthesise sub-agent outputs into a structured InsightReport.

    Reads all ``*_metrics`` keys and ``domain_context`` from *state*.
    Writes ``insight_report`` (InsightReport.model_dump()) back to *state*
    for ppt_agent to consume directly.
    """
    domain_context: dict = state.get("domain_context", {})
    if not domain_context:
        raise ValueError("insight_agent: 'domain_context' must be present in pipeline state")

    # Warn if no analysis results are available (all sub-agents still pending)
    available = [k for k, _ in _AGENT_KEYS if state.get(k)]
    if not available:
        logger.warning(
            "insight_agent: no sub-agent outputs found in state — "
            "report will be generated without quantitative data"
        )

    # Build prompt and call LLM
    human_content = _build_human_message(state)

    settings = get_settings()
    llm = ChatOpenAI(
        model="gpt-4o",           # use full model for synthesis quality
        temperature=0.2,          # slight creativity for narrative; still deterministic
        api_key=settings.OPENAI_API_KEY,
    ).with_structured_output(InsightReport, method="function_calling")

    insight_report: InsightReport = await llm.ainvoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
    )

    logger.info(
        "insight_agent: domain=%r  sentiment=%s  slides=%d  findings=%d",
        insight_report.domain,
        insight_report.overall_sentiment,
        len([s for s in insight_report.slide_order]),
        len(insight_report.top_findings),
    )

    return {"insight_report": insight_report.model_dump()}

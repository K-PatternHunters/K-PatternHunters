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
from datetime import datetime
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
  Format: "[구체적 액션] — 근거: [분석명]에서 [구체적 수치/패턴] 발견."
  예시: "checkout 페이지 UX 개선 우선 착수 — 근거: funnel 분석에서 begin_checkout 이탈률 51.2%(업계 평균 35% 대비 +16.2%p)"

overall_sentiment
  One of: positive / negative / neutral / mixed — based on the week's metrics vs benchmarks.

Per-slide content (performance, funnel, cohort, journey, anomaly, prediction)
  For each analysis that HAS data:
  - title: short slide title
  - headline: the single key message for this slide (one sentence, must include a key number)
  - bullets: 3-5 findings. EACH bullet MUST follow this format:
      "[지표명] [구체적 수치] — [전주/업계 기준과의 비교] → [비즈니스 의미 또는 원인 추정]"
      예시: "전환율 1.87% — 업계 기준(2%) 대비 0.13%p 미달, 장바구니 단계 이탈(72%)이 주요 원인"
      수치가 없는 bullet은 작성하지 마세요.
  - metrics: the most important 3-5 numbers to display prominently
  - chart_type: choose the best visual — funnel_chart / heatmap / sankey / \
line_chart / bar_chart / kpi_cards / table
  - chart_data_key: the PipelineState key for this analysis's raw data \
(e.g. "performance_metrics", "funnel_metrics")
  - speaker_notes: 해당 슬라이드에서 발표자가 강조해야 할 인과관계나 추가 맥락. \
단순 수치 반복이 아닌 "왜 이런 결과가 나왔는지"에 집중.

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
    week_start = state.get("week_start", "")
    week_end   = state.get("week_end", "")
    if week_start and week_end:
        try:
            s = datetime.strptime(week_start, "%Y%m%d")
            e = datetime.strptime(week_end, "%Y%m%d")
            period_str = f"{period} | {s.strftime('%Y-%m-%d')} ~ {e.strftime('%Y-%m-%d')}"
        except ValueError:
            period_str = f"{period} | {week_start} ~ {week_end}"
    else:
        period_str = period

    # ── Explicit WoW direction summary to prevent LLM contradicting the actual numbers ──
    wow_section = ""
    perf = state.get("performance_metrics") or {}
    wow = perf.get("wow_change") or {}
    kpis = perf.get("kpis") or {}
    if wow:
        def _dir(v) -> str:
            if v is None:
                return "데이터 없음"
            return f"{'증가(+)' if float(v) >= 0 else '감소(-)'} {abs(float(v))*100:.1f}%p"

        wow_lines = [
            f"  - 총 매출: ${kpis.get('total_revenue', 0):,.0f} | 전주 대비 {_dir(wow.get('total_revenue'))}",
            f"  - 거래 건수: {kpis.get('transaction_count', 0)} | 전주 대비 {_dir(wow.get('transaction_count'))}",
            f"  - 세션 수: {kpis.get('session_count', 0)} | 전주 대비 {_dir(wow.get('session_count'))}",
            f"  - 전환율: {kpis.get('conversion_rate', 0)*100:.2f}% | 전주 대비 {_dir(wow.get('conversion_rate'))}",
        ]
        wow_section = (
            "\n## ⚠ WoW 방향 요약 (이 수치와 모순되는 서술 절대 금지)\n"
            + "\n".join(wow_lines)
            + "\n위 방향(증가/감소)과 반대로 서술하면 안 됩니다. executive_summary와 bullets에서 반드시 이 방향과 일치하게 작성하세요.\n"
        )

    return f"""\
## Domain Context
{ctx_section}

## Analysis Period
{period_str}
{wow_section}
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

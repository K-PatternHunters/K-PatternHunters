"""Shared Pydantic v2 models for API request/response schemas and MongoDB document shapes."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field


def _keep(existing, new):
    """LangGraph reducer: retain existing value when node does not update the field."""
    return new if new is not None else existing


# ──────────────────────────────────────────────────────────────────────────────
# API request / response models
# ──────────────────────────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    period: Literal["daily", "weekly", "monthly"] = "weekly"
    domain_description: str
    week_start: str = ""   # YYYYMMDD — MongoDB query range start (inclusive)
    week_end: str = ""     # YYYYMMDD — MongoDB query range end (inclusive)
    log_ids: list[str] = []


class JobStatus(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"] = "pending"
    progress: int = 0          # 0-100
    result_url: str | None = None
    error: str | None = None


class AnalysisResult(BaseModel):
    job_id: str
    ppt_url: str | None = None
    summary: str | None = None


class RawLog(BaseModel):
    # Placeholder — map to actual GA4 event fields during schema_mapping_agent implementation
    event_date: str | None = None
    event_name: str | None = None
    user_pseudo_id: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Domain context — produced by context_agent, consumed by all downstream agents
# ──────────────────────────────────────────────────────────────────────────────

AVAILABLE_SUB_AGENTS: list[str] = [
    "funnel",
    "cohort",
    "journey",
    "performance",
    "anomaly",
    "prediction",
]

# Default GA4 e-commerce funnel steps (can be overridden per domain)
DEFAULT_FUNNEL_STEPS: list[str] = [
    "session_start",
    "view_item",
    "add_to_cart",
    "begin_checkout",
    "purchase",
]


# ── Per-agent config models ────────────────────────────────────────────────────

class FunnelConfig(BaseModel):
    """Configuration consumed by funnel_agent."""

    steps: list[str] = Field(
        default=DEFAULT_FUNNEL_STEPS,
        description=(
            "Ordered list of GA4 event names that define the conversion funnel. "
            "Defaults to the standard GA4 e-commerce sequence; adjust for the domain."
        ),
    )


class CohortConfig(BaseModel):
    """Configuration consumed by cohort_agent."""

    cohort_basis: str = Field(
        default="first_purchase_week",
        description="The event / milestone used to assign users to a cohort week.",
    )
    user_key: str = Field(
        default="user_pseudo_id",
        description="Log field that uniquely identifies a user across sessions.",
    )
    metrics: list[str] = Field(
        default=["retention_rate", "avg_revenue"],
        description="Per-week metrics to compute for each cohort.",
    )


class JourneyConfig(BaseModel):
    """Configuration consumed by journey_agent."""

    top_n: int = Field(
        default=10,
        description="Number of top paths to surface for each outcome category.",
    )
    max_depth: int = Field(
        default=5,
        description="Maximum number of events per path (session truncated at this depth).",
    )
    split_by_outcome: bool = Field(
        default=True,
        description=(
            "When True, report top_n converted paths and top_n abandoned paths separately."
        ),
    )


class PerformanceConfig(BaseModel):
    """Configuration consumed by performance_agent."""

    kpis: list[str] = Field(
        default=[
            "total_revenue",
            "transaction_count",
            "arpu",
            "session_count",
            "conversion_rate",
            "bounce_rate",
        ],
        description="KPI names to compute in the performance report.",
    )
    breakdowns: list[str] = Field(
        default=["traffic_source", "device_category"],
        description="Dimension fields by which each KPI is broken down.",
    )


class AnomalyConfig(BaseModel):
    """Configuration consumed by anomaly_agent."""

    target_metrics: list[str] = Field(
        default=["daily_revenue", "daily_session_count", "daily_conversion_rate"],
        description="Metric time-series to monitor for anomalies.",
    )
    method: str = Field(
        default="z_score",
        description="Statistical method used for anomaly detection.",
    )
    threshold: float = Field(
        default=2.0,
        description="Z-score magnitude above which a data point is flagged as anomalous.",
    )


class PredictionConfig(BaseModel):
    """Configuration consumed by prediction_agent."""

    targets: list[str] = Field(
        default=["next_week_revenue", "next_week_transaction_count"],
        description="Metrics to forecast for the upcoming week.",
    )
    method: str = Field(
        default="linear_trend",
        description="Forecasting method to apply.",
    )
    lookback_weeks: int = Field(
        default=4,
        description="Number of prior weeks used as the training window.",
    )


# ── Top-level domain context ───────────────────────────────────────────────────

class DomainContext(BaseModel):
    """Structured analysis context produced by context_agent.

    Serialised as a plain dict (via .model_dump()) and stored under the
    ``domain_context`` key of PipelineState so every downstream agent can
    read it without deserialising.
    """

    # ── Domain overview ────────────────────────────────────────────────────────
    domain: str = Field(
        description="Identified domain category (e.g. e-commerce, fintech, media, healthcare)"
    )
    domain_summary: str = Field(
        description="Brief description of the domain and its core user-behaviour patterns"
    )
    analysis_priorities: list[str] = Field(
        description=(
            "Ordered list of the most relevant analysis types for this domain. "
            f"Subset of {AVAILABLE_SUB_AGENTS}, most important first."
        )
    )
    recommended_sub_agents: list[str] = Field(
        description=f"Sub-agents to invoke; must be a subset of {AVAILABLE_SUB_AGENTS}"
    )

    # ── Interpretation & benchmarks ────────────────────────────────────────────
    key_metrics: dict[str, str] = Field(
        description="Domain-specific KPI definitions: metric_name -> plain-language description"
    )
    interpretation_guidelines: dict[str, str] = Field(
        description=(
            "How to interpret each recommended analysis type within this domain's "
            "business context (e.g. what conversion rate is 'good', which anomalies matter most)"
        )
    )
    industry_benchmarks: dict[str, Any] = Field(
        default_factory=dict,
        description="Known industry benchmark values for key metrics (used for comparison in reports)",
    )

    # ── Per-agent analysis configurations ─────────────────────────────────────
    funnel_config: FunnelConfig = Field(
        default_factory=FunnelConfig,
        description="Funnel step definitions; GA4 e-commerce defaults, adjust per domain.",
    )
    cohort_config: CohortConfig = Field(
        default_factory=CohortConfig,
        description="Cohort basis, user key, and per-week metrics to track.",
    )
    journey_config: JourneyConfig = Field(
        default_factory=JourneyConfig,
        description="Journey path settings: top-N, max depth, outcome split.",
    )
    performance_config: PerformanceConfig = Field(
        default_factory=PerformanceConfig,
        description="Performance KPI list and breakdown dimensions.",
    )
    anomaly_config: AnomalyConfig = Field(
        default_factory=AnomalyConfig,
        description="Anomaly detection targets, method, and Z-score threshold.",
    )
    prediction_config: PredictionConfig = Field(
        default_factory=PredictionConfig,
        description="Prediction targets, method, and lookback window.",
    )

    # ── Schema hints & references ──────────────────────────────────────────────
    log_schema_hints: dict[str, str] = Field(
        default_factory=dict,
        description="Raw log field names mapped to their semantic meaning in this domain",
    )
    rag_references: list[str] = Field(
        default_factory=list,
        description="Source document titles/IDs retrieved from the RAG knowledge base",
    )
    search_references: list[str] = Field(
        default_factory=list,
        description="Web-search snippets or URLs used to enrich the context",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Insight report — produced by insight_agent, consumed by ppt_agent
# ──────────────────────────────────────────────────────────────────────────────

class SlideContent(BaseModel):
    """Ready-to-render content for a single PPT slide.

    ppt_agent can consume this directly without re-interpreting data.
    """

    slide_type: str = Field(
        description=(
            "Slide category. One of: title, executive_summary, performance, "
            "funnel, cohort, journey, anomaly, prediction, recommendations"
        )
    )
    title: str = Field(description="Slide title text")
    headline: str = Field(
        description="One-sentence key message for this slide (displayed as sub-title or callout)"
    )
    bullets: list[str] = Field(
        description="Supporting bullet points (3-5 items)"
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Key numeric values to display on the slide. "
            "Keys are metric names, values are numbers or formatted strings."
        ),
    )
    chart_type: str = Field(
        description=(
            "Recommended chart/visual type for this slide. "
            "e.g. funnel_chart, heatmap, sankey, line_chart, bar_chart, kpi_cards, table"
        )
    )
    chart_data_key: str = Field(
        description=(
            "The PipelineState key that holds the raw data for the chart "
            "(e.g. funnel_metrics, cohort_metrics). "
            "ppt_agent uses this to pull chart data."
        )
    )
    speaker_notes: str = Field(
        default="",
        description="Additional context or speaking points — not shown on the slide itself",
    )


class InsightReport(BaseModel):
    """Structured output from insight_agent.

    Contains all content needed by ppt_agent to generate slides without
    additional LLM calls or data re-interpretation.
    Serialised via .model_dump() and stored under ``insight_report`` in PipelineState.
    """

    # ── Report meta ───────────────────────────────────────────────────────────
    domain: str = Field(description="Domain category (from domain_context)")
    analysis_period: str = Field(description="e.g. '2024-W12 (Mar 18–24)'")
    overall_sentiment: Literal["positive", "negative", "neutral", "mixed"] = Field(
        description="Overall tone of the week's performance"
    )

    # ── Executive layer ────────────────────────────────────────────────────────
    executive_summary: str = Field(
        description="3-5 sentence narrative summarising the week's most important findings"
    )
    top_findings: list[str] = Field(
        description="Top 3-5 key findings across all analyses, in priority order"
    )
    recommendations: list[str] = Field(
        description="Top 3-5 specific, actionable recommendations based on the findings"
    )

    # ── Per-analysis slide contents ────────────────────────────────────────────
    performance_slide: SlideContent | None = Field(
        default=None,
        description="Slide content for performance KPIs; None if analysis did not run",
    )
    funnel_slide: SlideContent | None = Field(
        default=None,
        description="Slide content for funnel analysis; None if analysis did not run",
    )
    cohort_slide: SlideContent | None = Field(
        default=None,
        description="Slide content for cohort/retention; None if analysis did not run",
    )
    journey_slide: SlideContent | None = Field(
        default=None,
        description="Slide content for user journey paths; None if analysis did not run",
    )
    anomaly_slide: SlideContent | None = Field(
        default=None,
        description="Slide content for anomaly findings; None if analysis did not run",
    )
    prediction_slide: SlideContent | None = Field(
        default=None,
        description="Slide content for next-week forecast; None if analysis did not run",
    )

    # ── Cross-analysis findings ────────────────────────────────────────────────
    cross_analysis_findings: list[str] = Field(
        default_factory=list,
        description=(
            "Insights that emerge from combining multiple analyses "
            "(e.g. funnel drop-off corroborated by anomaly detection)"
        ),
    )

    # ── PPT assembly hints ─────────────────────────────────────────────────────
    slide_order: list[str] = Field(
        description=(
            "Recommended slide sequence for ppt_agent. "
            "e.g. ['title','executive_summary','performance','funnel',...,'recommendations']"
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# LangGraph pipeline state
# ──────────────────────────────────────────────────────────────────────────────

class PipelineState(TypedDict, total=False):
    """Shared state dict passed through every node of the LangGraph pipeline."""

    # ── inputs ────────────────────────────────────────────────────────────────
    # str/dict fields use _keep reducer so LangGraph preserves them when nodes
    # do not explicitly return the key (LangGraph 1.x resets unwritten str fields to None).
    job_id: Annotated[str, _keep]
    period: Annotated[str, _keep]               # "daily" | "weekly" | "monthly"
    domain_description: Annotated[str, _keep]
    raw_logs: list[dict]                         # raw weekly log records
    log_ids: list[str]                           # MongoDB IDs of raw log documents
    week_start: Annotated[str, _keep]            # "YYYYMMDD"
    week_end: Annotated[str, _keep]              # "YYYYMMDD"

    # ── context_agent output ──────────────────────────────────────────────────
    domain_context: Annotated[dict, _keep]       # DomainContext.model_dump()

    # ── supervisor output ─────────────────────────────────────────────────────
    sub_agents_plan: list[str]                   # ordered list of sub-agent names to run

    # ── schema_mapping_agent output ───────────────────────────────────────────
    normalized_logs: list[dict]
    field_mapping: Annotated[dict, _keep]

    # ── sub-agent outputs ─────────────────────────────────────────────────────
    funnel_metrics: Annotated[dict, _keep]
    cohort_metrics: Annotated[dict, _keep]
    journey_metrics: Annotated[dict, _keep]
    performance_metrics: Annotated[dict, _keep]
    anomaly_metrics: Annotated[dict, _keep]
    prediction_metrics: Annotated[dict, _keep]

    # ── insight_agent output ──────────────────────────────────────────────────
    insight_report: Annotated[dict, _keep]

    # ── ppt_agent output ──────────────────────────────────────────────────────
    ppt_url: Annotated[str, _keep]

"""context_agent — generates structured domain analysis context from weekly log data.

Input  (PipelineState keys consumed):
    domain_description : str          — domain category / description supplied by the user
    raw_logs           : list[dict]   — weekly raw log records (GA4 or similar)

Output (PipelineState key produced):
    domain_context     : dict         — DomainContext.model_dump(); consumed by supervisor
                                        and all downstream analysis / PPT agents
"""

from __future__ import annotations

import asyncio
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.models import DomainContext

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Prompt
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior data-analytics consultant specialising in user-behaviour analysis.

Given:
- A business domain description
- A sample of the user's weekly log data (field names + example rows)
- Optional references from a past-report knowledge base (RAG)
- Optional live industry research (web search)

Your task is to produce a **structured analysis context** that will guide a set of \
automated data-analysis agents and a PPT generation pipeline.

The context serves two purposes:
1. **Guide which analyses to run and in what priority** — which agent types are most
   relevant for this domain (funnel, cohort, journey, performance, anomaly, prediction),
   what KPIs to track, and what domain-specific metrics to focus on.
2. **Guide how to interpret the results** — what good/bad values look like in this domain,
   known industry benchmarks, and what business decisions each analysis should support.

════════════════════════════════════════════════════
MANDATORY ANALYSIS CONFIGURATION FIELDS
════════════════════════════════════════════════════
You MUST populate all six per-agent config objects. Use the defaults below for standard
e-commerce; override only when the domain or log schema clearly requires a different setup.

funnel_config.steps
  Default (GA4 e-commerce): ["session_start","view_item","add_to_cart","begin_checkout","purchase"]
  Override: add domain-specific steps (e.g. "view_promotion") or remove irrelevant ones
  (e.g. no "add_to_cart" for a pure content/media domain).

cohort_config
  cohort_basis default: "first_purchase_week"
  user_key default: "user_pseudo_id"
  metrics default: ["retention_rate", "avg_revenue"]

journey_config
  top_n default: 10  (top paths per outcome category)
  max_depth default: 5  (max events per path)
  split_by_outcome default: true  (separate converted vs. abandoned paths)

performance_config
  kpis default: ["total_revenue","transaction_count","arpu",
                 "session_count","conversion_rate","bounce_rate"]
  breakdowns default: ["traffic_source","device_category"]
  Add domain-relevant dimensions if the log data supports them.

anomaly_config
  target_metrics default: ["daily_revenue","daily_session_count","daily_conversion_rate"]
  method default: "z_score"
  threshold default: 2.0

prediction_config
  targets default: ["next_week_revenue","next_week_transaction_count"]
  method default: "linear_trend"
  lookback_weeks default: 4

════════════════════════════════════════════════════
ADDITIONAL REQUIRED FIELDS
════════════════════════════════════════════════════
- key_metrics: domain-specific KPI definitions
- interpretation_guidelines: how to read each analysis type in this domain's context
- industry_benchmarks: known baseline values for comparison in reports
- log_schema_hints: map raw log field names to their semantic meaning

Be concise but precise. The output is consumed by automated agents, not humans."""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_log_summary(raw_logs: list[dict], max_rows: int = 20) -> str:
    """Return a compact JSON representation of the log sample for the prompt."""
    if not raw_logs:
        return "(no log data provided)"
    sample = raw_logs[:max_rows]
    schema_fields = list(sample[0].keys())
    return json.dumps(
        {"schema_fields": schema_fields, "sample_rows": sample},
        ensure_ascii=False,
        indent=2,
    )


async def _try_rag(domain_description: str) -> list[str]:
    """Attempt RAG retrieval; silently return [] if the tool is not yet implemented."""
    try:
        from app.tools.rag_tool import rag_search  # noqa: PLC0415

        results = await rag_search(query=domain_description)
        return [str(r) for r in results]
    except NotImplementedError:
        logger.debug("rag_search not yet implemented — skipping RAG step")
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG retrieval failed: %s", exc)
        return []


async def _try_web_search(domain_description: str) -> list[str]:
    """Attempt web search; silently return [] if the tool is not yet implemented."""
    try:
        from app.tools.web_search_tool import web_search  # noqa: PLC0415

        results = await web_search(
            query=f"{domain_description} user behaviour analytics KPIs benchmarks"
        )
        return [str(r) for r in results]
    except NotImplementedError:
        logger.debug("web_search not yet implemented — skipping web-search step")
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Web search failed: %s", exc)
        return []


def _build_human_message(
    domain_description: str,
    log_summary: str,
    rag_refs: list[str],
    search_refs: list[str],
) -> str:
    rag_section = (
        "\n".join(f"- {r}" for r in rag_refs) if rag_refs else "(none retrieved)"
    )
    search_section = (
        "\n".join(f"- {r}" for r in search_refs) if search_refs else "(none retrieved)"
    )
    return f"""\
## Domain Description
{domain_description}

## Weekly Log Data Sample
{log_summary}

## Past Report References (RAG)
{rag_section}

## Live Industry Research (Web Search)
{search_section}

Please produce the structured domain analysis context based on the information above."""


# ──────────────────────────────────────────────────────────────────────────────
# Agent entry point
# ──────────────────────────────────────────────────────────────────────────────

async def context_agent(state: dict) -> dict:
    """LangGraph node: generate domain analysis context.

    Reads  ``domain_description`` and ``raw_logs`` from *state*.
    Writes ``domain_context`` (a plain dict from DomainContext.model_dump()) back
    to *state* so the supervisor and all sub-agents can consume it.
    """
    domain_description: str = state.get("domain_description", "")
    raw_logs: list[dict] = state.get("raw_logs", [])

    if not domain_description:
        raise ValueError("context_agent: 'domain_description' must be present in pipeline state")

    # 1. Gather supporting evidence in parallel (best-effort; failures are silent)
    rag_refs, search_refs = await asyncio.gather(
        _try_rag(domain_description),
        _try_web_search(domain_description),
    )

    # 2. Build prompt
    log_summary = _build_log_summary(raw_logs)
    human_content = _build_human_message(
        domain_description, log_summary, rag_refs, search_refs
    )

    # 3. Call LLM with structured output (forces response to match DomainContext schema)
    settings = get_settings()
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=settings.OPENAI_API_KEY,
    ).with_structured_output(DomainContext)

    domain_context: DomainContext = await llm.ainvoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
    )

    # 4. Attach reference lists gathered outside the LLM call
    if rag_refs:
        domain_context.rag_references = rag_refs
    if search_refs:
        domain_context.search_references = search_refs

    logger.info(
        "context_agent: domain=%r  recommended_agents=%s",
        domain_context.domain,
        domain_context.recommended_sub_agents,
    )

    # 5. Serialise to plain dict for LangGraph state
    return {"domain_context": domain_context.model_dump()}

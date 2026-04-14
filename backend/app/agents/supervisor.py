"""Supervisor agent — receives domain context and routes to schema_mapping then 6 analysis agents.

Input  (PipelineState keys consumed):
    domain_context : dict   — DomainContext.model_dump() from context_agent

Output (PipelineState keys produced):
    sub_agents_plan : list[str]   — ordered list of sub-agent names to run
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_ALL_SUB_AGENTS: list[str] = [
    "funnel",
    "cohort",
    "journey",
    "performance",
    "anomaly",
    "prediction",
]


async def supervisor(state: dict) -> dict:
    """LangGraph node: deterministic routing, no LLM call.

    Context Agent has already determined the domain and recommended sub-agents.
    Supervisor always runs all 6 analysis agents — schema_mapping runs first,
    then the 6 agents fan out in parallel (handled by LangGraph edges in pipeline.py).
    """
    domain_context: dict = state.get("domain_context", {})
    recommended = domain_context.get("recommended_sub_agents", _ALL_SUB_AGENTS)

    # Ensure only valid agent names pass through
    plan = [a for a in _ALL_SUB_AGENTS if a in recommended]
    if not plan:
        logger.warning("supervisor: recommended_sub_agents was empty — running all agents")
        plan = list(_ALL_SUB_AGENTS)

    logger.info("supervisor: sub_agents_plan=%s", plan)
    return {"sub_agents_plan": plan}

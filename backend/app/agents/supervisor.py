"""Supervisor agent — receives domain context, creates an analysis plan, and delegates tasks to sub-agents."""

# TODO: use LangGraph StateGraph with a supervisor node pattern
# TODO: inspect domain_context and raw_log schema; decide which sub-agents to invoke
# TODO: fan out to sub-agents in parallel where possible (LangGraph parallel branches)
# TODO: collect sub-agent outputs and pass them to insight_agent

from langchain_core.messages import SystemMessage  # langchain v1.0+ import path


async def supervisor(state: dict) -> dict:
    # Placeholder — implementation pending
    raise NotImplementedError

"""Funnel Analysis Agent — step-level conversion and drop-off rates.

Input  (PipelineState keys consumed):
    week_start     : str        — "YYYYMMDD"
    week_end       : str        — "YYYYMMDD"
    field_mapping  : dict       — from schema_mapping_agent
    raw_logs       : list[dict] — weekly raw log records
    domain_context : dict       — DomainContext.model_dump()

Output (PipelineState keys produced):
    funnel_metrics : dict
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.agents._ga4_utils import get_device_category, get_traffic_source, in_range

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_breakdown_value(doc: dict, breakdown: str) -> str:
    if breakdown == "device_category":
        return get_device_category(doc)
    if breakdown == "traffic_source":
        return get_traffic_source(doc)
    return "unknown"


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------

def _aggregate_funnel(
    raw_logs: list[dict],
    week_start: str,
    week_end: str,
    steps: list[str],
    breakdowns: list[str],
) -> dict:
    step_users: dict[str, set] = {s: set() for s in steps}
    breakdown_users: dict[str, dict[str, dict[str, set]]] = {
        b: defaultdict(lambda: {s: set() for s in steps}) for b in breakdowns
    }

    for doc in raw_logs:
        event_date = doc.get("event_date", "")
        if not in_range(event_date, week_start, week_end):
            continue
        event_name = doc.get("event_name", "")
        if event_name not in steps:
            continue
        uid = doc.get("user_pseudo_id", "")
        if not uid:
            continue

        step_users[event_name].add(uid)

        for bd in breakdowns:
            dim_val = _get_breakdown_value(doc, bd)
            breakdown_users[bd][dim_val][event_name].add(uid)

    return {"step_users": step_users, "breakdown_users": breakdown_users}


def _build_step_stats(steps: list[str], step_users: dict[str, set]) -> list[dict]:
    first_count = len(step_users.get(steps[0], set())) if steps else 0
    result = []
    prev_count = first_count
    for i, step in enumerate(steps):
        count = len(step_users.get(step, set()))
        drop_off_rate = round((prev_count - count) / prev_count * 100, 2) if prev_count > 0 and i > 0 else 0.0
        conversion_rate = round(count / first_count, 4) if first_count > 0 else 0.0
        result.append({
            "event_name": step,
            "user_count": count,
            "drop_off_rate": drop_off_rate,
            "conversion_rate": conversion_rate,
        })
        prev_count = count
    return result


def _biggest_drop_off(steps: list[str], step_stats: list[dict]) -> str:
    if len(step_stats) < 2:
        return ""
    max_drop = max(step_stats[1:], key=lambda s: s["drop_off_rate"], default=None)
    if not max_drop:
        return ""
    idx = next(i for i, s in enumerate(step_stats) if s["event_name"] == max_drop["event_name"])
    return f"{steps[idx - 1]} → {steps[idx]}"


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def funnel_agent(state: dict) -> dict:
    """LangGraph node: compute funnel conversion and drop-off rates."""
    week_start: str = state.get("week_start", "")
    week_end: str = state.get("week_end", "")
    raw_logs: list[dict] = state.get("raw_logs", [])
    domain_context: dict = state.get("domain_context", {})

    funnel_cfg: dict = domain_context.get("funnel_config", {})
    steps: list[str] = funnel_cfg.get("steps", [
        "session_start", "view_item", "add_to_cart", "begin_checkout", "purchase"
    ])
    breakdowns: list[str] = domain_context.get("performance_config", {}).get(
        "breakdowns", ["traffic_source", "device_category"]
    )

    agg = _aggregate_funnel(raw_logs, week_start, week_end, steps, breakdowns)
    step_users = agg["step_users"]
    breakdown_users = agg["breakdown_users"]

    step_stats = _build_step_stats(steps, step_users)
    first_count = step_stats[0]["user_count"] if step_stats else 0
    last_count = step_stats[-1]["user_count"] if step_stats else 0
    overall_cvr = round(last_count / first_count, 4) if first_count > 0 else 0.0

    breakdowns_result: dict[str, dict] = {}
    for bd in breakdowns:
        breakdowns_result[bd] = {}
        for dim_val, dim_step_users in breakdown_users[bd].items():
            bd_stats = _build_step_stats(steps, dim_step_users)
            bd_first = bd_stats[0]["user_count"] if bd_stats else 0
            bd_last = bd_stats[-1]["user_count"] if bd_stats else 0
            breakdowns_result[bd][dim_val] = {
                "overall_conversion_rate": round(bd_last / bd_first, 4) if bd_first > 0 else 0.0,
                "steps": bd_stats,
            }

    funnel_metrics = {
        "steps": step_stats,
        "overall_conversion_rate": overall_cvr,
        "biggest_drop_off_step": _biggest_drop_off(steps, step_stats),
        "breakdowns": breakdowns_result,
    }

    logger.info(
        "funnel_agent: overall_cvr=%.4f  biggest_drop_off=%s",
        overall_cvr,
        funnel_metrics["biggest_drop_off_step"],
    )
    return {"funnel_metrics": funnel_metrics}

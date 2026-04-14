"""Funnel Analysis Agent — step-level conversion and drop-off rates.

Input  (PipelineState keys consumed):
    week_start     : str  — "YYYYMMDD"
    week_end       : str  — "YYYYMMDD"
    domain_context : dict — DomainContext.model_dump()

Output (PipelineState keys produced):
    funnel_metrics : dict
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.agents._ga4_utils import PREPROCESS_STAGE
from app.agents._agent_utils import error_patch, validate_or_retry
from app.core.models import FunnelMetrics
from app.db.mongo import get_collection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step stats builder (pure Python — runs on aggregation results)
# ---------------------------------------------------------------------------

def _build_step_stats(steps: list[str], step_users: dict[str, int]) -> list[dict]:
    first_count = step_users.get(steps[0], 0) if steps else 0
    result = []
    prev_count = first_count
    for i, step in enumerate(steps):
        count = step_users.get(step, 0)
        drop_off_rate = (
            round((prev_count - count) / prev_count * 100, 2)
            if prev_count > 0 and i > 0
            else 0.0
        )
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
# Business-logic validation
# ---------------------------------------------------------------------------

def _validate(metrics: dict) -> list[str]:
    errors: list[str] = []
    steps = metrics.get("steps", [])
    if not steps:
        errors.append("steps 리스트가 비어 있음 — week_start/week_end 범위에 해당 이벤트가 없음")
        return errors
    first_count = steps[0].get("user_count", 0)
    if first_count == 0:
        errors.append(
            f"첫 단계({steps[0].get('event_name', '?')}) user_count == 0 "
            "— 데이터 범위 또는 event_name 불일치 확인 필요"
        )
    return errors


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def funnel_agent(state: dict) -> dict:
    """LangGraph node: compute funnel conversion and drop-off rates via MongoDB aggregation."""
    domain_context: dict = state.get("domain_context", {})
    funnel_cfg: dict = domain_context.get("funnel_config", {})
    steps: list[str] = funnel_cfg.get("steps", [
        "session_start", "view_item", "add_to_cart", "begin_checkout", "purchase"
    ])

    async def _run(s: dict) -> tuple[dict, list[str]]:
        week_start: str = s.get("week_start", "")
        week_end: str = s.get("week_end", "")
        col = get_collection("raw_logs")

        # ── Step-level unique user counts ──────────────────────────────────────
        step_pipeline = [
            {"$match": {
                "event_date": {"$gte": week_start, "$lte": week_end},
                "event_name": {"$in": steps},
            }},
            PREPROCESS_STAGE,
            {"$group": {
                "_id": "$event_name",
                "users": {"$addToSet": "$user_pseudo_id"},
            }},
            {"$project": {
                "event_name": "$_id",
                "user_count": {"$size": "$users"},
                "_id": 0,
            }},
        ]
        step_docs = await col.aggregate(step_pipeline).to_list(length=None)
        step_users: dict[str, int] = {d["event_name"]: d["user_count"] for d in step_docs}

        step_stats = _build_step_stats(steps, step_users)
        first_count = step_stats[0]["user_count"] if step_stats else 0
        last_count = step_stats[-1]["user_count"] if step_stats else 0
        overall_cvr = round(last_count / first_count, 4) if first_count > 0 else 0.0

        # ── Breakdowns via $facet ──────────────────────────────────────────────
        facet_pipeline = [
            {"$match": {
                "event_date": {"$gte": week_start, "$lte": week_end},
                "event_name": {"$in": steps},
            }},
            PREPROCESS_STAGE,
            {"$facet": {
                "by_device": [
                    {"$group": {
                        "_id": {"event": "$event_name", "device": "$device.category"},
                        "users": {"$addToSet": "$user_pseudo_id"},
                    }},
                    {"$project": {
                        "event_name": "$_id.event",
                        "device": "$_id.device",
                        "user_count": {"$size": "$users"},
                        "_id": 0,
                    }},
                ],
                "by_source": [
                    {"$group": {
                        "_id": {"event": "$event_name", "source": "$traffic_source.source"},
                        "users": {"$addToSet": "$user_pseudo_id"},
                    }},
                    {"$project": {
                        "event_name": "$_id.event",
                        "source": "$_id.source",
                        "user_count": {"$size": "$users"},
                        "_id": 0,
                    }},
                ],
            }},
        ]
        facet_docs = await col.aggregate(facet_pipeline).to_list(length=None)
        facet = facet_docs[0] if facet_docs else {"by_device": [], "by_source": []}

        # Build breakdown step_users dicts
        def _facet_to_breakdowns(rows: list[dict], dim_key: str) -> dict[str, dict[str, int]]:
            result: dict[str, dict[str, int]] = {}
            for row in rows:
                dim_val = row.get(dim_key) or "unknown"
                event = row.get("event_name", "")
                result.setdefault(dim_val, {})[event] = row.get("user_count", 0)
            return result

        device_bd = _facet_to_breakdowns(facet["by_device"], "device")
        source_bd = _facet_to_breakdowns(facet["by_source"], "source")

        breakdowns_result: dict[str, dict] = {
            "device_category": {},
            "traffic_source": {},
        }
        for dim_val, su in device_bd.items():
            bd_stats = _build_step_stats(steps, su)
            bd_first = bd_stats[0]["user_count"] if bd_stats else 0
            bd_last = bd_stats[-1]["user_count"] if bd_stats else 0
            breakdowns_result["device_category"][dim_val] = {
                "overall_conversion_rate": round(bd_last / bd_first, 4) if bd_first > 0 else 0.0,
                "steps": bd_stats,
            }
        for dim_val, su in source_bd.items():
            bd_stats = _build_step_stats(steps, su)
            bd_first = bd_stats[0]["user_count"] if bd_stats else 0
            bd_last = bd_stats[-1]["user_count"] if bd_stats else 0
            breakdowns_result["traffic_source"][dim_val] = {
                "overall_conversion_rate": round(bd_last / bd_first, 4) if bd_first > 0 else 0.0,
                "steps": bd_stats,
            }

        metrics = {
            "steps": step_stats,
            "overall_conversion_rate": overall_cvr,
            "biggest_drop_off_step": _biggest_drop_off(steps, step_stats),
            "breakdowns": breakdowns_result,
        }
        return metrics, _validate(metrics)

    funnel_metrics, validation_errors = await validate_or_retry(
        run_fn=_run,
        state=state,
        agent_name="funnel_agent",
        state_key="funnel_metrics",
    )

    logger.info(
        "funnel_agent: overall_cvr=%.4f  biggest_drop_off=%s",
        funnel_metrics.get("overall_conversion_rate", 0),
        funnel_metrics.get("biggest_drop_off_step", ""),
    )

    try:
        FunnelMetrics(**funnel_metrics)
    except ValidationError as exc:
        logger.warning("funnel_agent: schema validation failed — %s", exc)

    return {"funnel_metrics": funnel_metrics, **error_patch("funnel_agent", validation_errors)}

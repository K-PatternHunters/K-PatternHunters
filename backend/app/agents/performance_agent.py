"""Performance Analysis Agent — weekly KPI aggregation with breakdowns and WoW change.

Input  (PipelineState keys consumed):
    week_start     : str        — "YYYYMMDD"
    week_end       : str        — "YYYYMMDD"
    field_mapping  : dict       — from schema_mapping_agent
    raw_logs       : list[dict] — weekly raw log records (current week + prior week for WoW)
    domain_context : dict       — DomainContext.model_dump()

Output (PipelineState keys produced):
    performance_metrics : dict
"""

from __future__ import annotations

import logging
from collections import defaultdict

from pydantic import ValidationError

from app.core.models import PerformanceMetrics
from app.agents._agent_utils import error_patch, validate_or_retry
from app.agents._ga4_utils import (
    get_device_category,
    get_purchase_revenue,
    get_session_id,
    get_traffic_source,
    get_transaction_id,
    in_range,
    shift_days,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Aggregation kernel — reusable for current week and prior week
# ---------------------------------------------------------------------------

def _aggregate_week(raw_logs: list[dict], start: str, end: str) -> dict:
    """Aggregate all KPI data for docs within [start, end]."""
    total_revenue = 0.0
    transaction_ids: set[str] = set()
    session_ids: set[str] = set()
    user_ids: set[str] = set()
    bounce_sessions: set[str] = set()  # sessions with only 1 event
    session_event_count: dict[str, int] = defaultdict(int)

    # daily
    daily: dict[str, dict] = defaultdict(lambda: {
        "revenue": 0.0, "transaction_ids": set(), "session_ids": set()
    })

    # by traffic source
    by_source: dict[str, dict] = defaultdict(lambda: {
        "session_ids": set(), "transaction_ids": set(), "revenue": 0.0
    })

    # by device
    by_device: dict[str, dict] = defaultdict(lambda: {
        "session_ids": set(), "transaction_ids": set(), "revenue": 0.0
    })

    # by item category: {category: {view, add_to_cart, purchase, revenue}}
    by_category: dict[str, dict] = defaultdict(lambda: {
        "view_count": 0, "add_to_cart_count": 0, "purchase_count": 0, "revenue": 0.0
    })

    for doc in raw_logs:
        event_date = doc.get("event_date", "")
        if not in_range(event_date, start, end):
            continue

        event_name = doc.get("event_name", "")
        uid = doc.get("user_pseudo_id", "")
        sid = get_session_id(doc)
        source = get_traffic_source(doc)
        device = get_device_category(doc)

        if uid:
            user_ids.add(uid)
        if sid:
            session_ids.add(sid)
            session_event_count[sid] += 1
            by_source[source]["session_ids"].add(sid)
            by_device[device]["session_ids"].add(sid)
            daily[event_date]["session_ids"].add(sid)

        if event_name == "purchase":
            revenue = get_purchase_revenue(doc)
            txn_id = get_transaction_id(doc)
            total_revenue += revenue
            if txn_id:
                transaction_ids.add(txn_id)
                by_source[source]["transaction_ids"].add(txn_id)
                by_device[device]["transaction_ids"].add(txn_id)
                daily[event_date]["transaction_ids"].add(txn_id)
            by_source[source]["revenue"] += revenue
            by_device[device]["revenue"] += revenue
            daily[event_date]["revenue"] += revenue

        # Item category breakdowns
        if event_name in ("view_item", "add_to_cart", "purchase"):
            items = doc.get("items") or []
            for item in items:
                category = item.get("item_category") or "unknown"
                if event_name == "view_item":
                    by_category[category]["view_count"] += 1
                elif event_name == "add_to_cart":
                    by_category[category]["add_to_cart_count"] += 1
                elif event_name == "purchase":
                    by_category[category]["purchase_count"] += 1
                    try:
                        by_category[category]["revenue"] += float(item.get("price", 0) or 0) * float(item.get("quantity", 1) or 1)
                    except (TypeError, ValueError):
                        pass

    # Bounce sessions: sessions with only 1 event total
    bounce_sessions = {sid for sid, cnt in session_event_count.items() if cnt == 1}

    session_count = len(session_ids)
    transaction_count = len(transaction_ids)

    return {
        "total_revenue": round(total_revenue, 2),
        "transaction_count": transaction_count,
        "session_count": session_count,
        "user_count": len(user_ids),
        "bounce_session_count": len(bounce_sessions),
        "daily": daily,
        "by_source": by_source,
        "by_device": by_device,
        "by_category": by_category,
    }


def _compute_kpis(agg: dict) -> dict:
    session_count = agg["session_count"]
    transaction_count = agg["transaction_count"]
    total_revenue = agg["total_revenue"]
    user_count = agg["user_count"]
    bounce_count = agg["bounce_session_count"]

    arpu = round(total_revenue / user_count, 4) if user_count > 0 else 0.0
    cvr = round(transaction_count / session_count, 4) if session_count > 0 else 0.0
    bounce_rate = round(bounce_count / session_count, 4) if session_count > 0 else 0.0

    return {
        "total_revenue": total_revenue,
        "transaction_count": transaction_count,
        "arpu": arpu,
        "session_count": session_count,
        "conversion_rate": cvr,
        "bounce_rate": bounce_rate,
    }


# ---------------------------------------------------------------------------
# Business-logic validation
# ---------------------------------------------------------------------------

def _validate(metrics: dict) -> list[str]:
    errors: list[str] = []
    kpis = metrics.get("kpis", {})
    if kpis.get("session_count", 0) == 0:
        errors.append(
            "session_count == 0 — 해당 기간에 session_id를 가진 이벤트가 없음, "
            "week_start/week_end 범위 또는 raw_logs 데이터 확인 필요"
        )
    return errors


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def performance_agent(state: dict) -> dict:
    """LangGraph node: aggregate weekly KPIs with breakdowns and WoW change."""

    async def _run(s: dict) -> tuple[dict, list[str]]:
        week_start: str = s.get("week_start", "")
        week_end: str = s.get("week_end", "")
        raw_logs: list[dict] = s.get("raw_logs", [])

        agg = _aggregate_week(raw_logs, week_start, week_end)
        kpis = _compute_kpis(agg)

        daily_breakdown = []
        for date in sorted(agg["daily"].keys()):
            d = agg["daily"][date]
            daily_breakdown.append({
                "date": date,
                "revenue": round(d["revenue"], 2),
                "transaction_count": len(d["transaction_ids"]),
                "session_count": len(d["session_ids"]),
            })

        by_traffic_source = []
        for source, d in sorted(agg["by_source"].items(), key=lambda x: -len(x[1]["session_ids"])):
            sc = len(d["session_ids"])
            tc = len(d["transaction_ids"])
            by_traffic_source.append({
                "source": source,
                "session_count": sc,
                "transaction_count": tc,
                "revenue": round(d["revenue"], 2),
                "conversion_rate": round(tc / sc, 4) if sc > 0 else 0.0,
            })

        by_device_category = []
        for device, d in sorted(agg["by_device"].items(), key=lambda x: -len(x[1]["session_ids"])):
            sc = len(d["session_ids"])
            tc = len(d["transaction_ids"])
            by_device_category.append({
                "device": device,
                "session_count": sc,
                "transaction_count": tc,
                "revenue": round(d["revenue"], 2),
                "conversion_rate": round(tc / sc, 4) if sc > 0 else 0.0,
            })

        by_item_category = []
        for category, d in sorted(agg["by_category"].items(), key=lambda x: -x[1]["revenue"]):
            vc = d["view_count"]
            by_item_category.append({
                "category": category,
                "view_count": vc,
                "add_to_cart_count": d["add_to_cart_count"],
                "purchase_count": d["purchase_count"],
                "revenue": round(d["revenue"], 2),
                "purchase_rate": round(d["purchase_count"] / vc, 4) if vc > 0 else 0.0,
            })

        prior_start = shift_days(week_start, -7)
        prior_end = shift_days(week_end, -7)
        prior_agg = _aggregate_week(raw_logs, prior_start, prior_end)
        prior_kpis = _compute_kpis(prior_agg)

        wow_change: dict | None = None
        if prior_kpis["session_count"] > 0:
            def _wow(curr, prev):
                return round((curr - prev) / prev, 4) if prev != 0 else None

            wow_change = {
                "total_revenue": _wow(kpis["total_revenue"], prior_kpis["total_revenue"]),
                "transaction_count": _wow(kpis["transaction_count"], prior_kpis["transaction_count"]),
                "session_count": _wow(kpis["session_count"], prior_kpis["session_count"]),
                "conversion_rate": _wow(kpis["conversion_rate"], prior_kpis["conversion_rate"]),
            }

        metrics = {
            "period": {"week_start": week_start, "week_end": week_end},
            "kpis": kpis,
            "daily_breakdown": daily_breakdown,
            "by_traffic_source": by_traffic_source,
            "by_device_category": by_device_category,
            "by_item_category": by_item_category,
            "wow_change": wow_change,
        }
        return metrics, _validate(metrics)

    performance_metrics, validation_errors = await validate_or_retry(
        run_fn=_run,
        state=state,
        agent_name="performance_agent",
        state_key="performance_metrics",
    )

    kpis = performance_metrics.get("kpis", {})
    logger.info(
        "performance_agent: revenue=%.2f  transactions=%d  cvr=%.4f",
        kpis.get("total_revenue", 0),
        kpis.get("transaction_count", 0),
        kpis.get("conversion_rate", 0),
    )

    try:
        PerformanceMetrics(**performance_metrics)
    except ValidationError as exc:
        logger.warning("performance_agent: schema validation failed — %s", exc)

    return {"performance_metrics": performance_metrics, **error_patch("performance_agent", validation_errors)}

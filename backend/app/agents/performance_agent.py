"""Performance Analysis Agent — weekly KPI aggregation with breakdowns and WoW change.

Input  (PipelineState keys consumed):
    week_start     : str  — "YYYYMMDD"
    week_end       : str  — "YYYYMMDD"
    domain_context : dict — DomainContext.model_dump()

Output (PipelineState keys produced):
    performance_metrics : dict
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.core.models import PerformanceMetrics
from app.agents._agent_utils import error_patch, validate_or_retry
from app.agents._ga4_utils import PREPROCESS_STAGE, shift_days
from app.db.mongo import get_collection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MongoDB aggregation
# ---------------------------------------------------------------------------

async def _aggregate_week(col, start: str, end: str) -> dict:
    """Run a $facet aggregation for KPI breakdowns in [start, end]."""
    pipeline = [
        {"$match": {"event_date": {"$gte": start, "$lte": end}}},
        PREPROCESS_STAGE,
        {"$facet": {
            # ── Overall KPIs ────────────────────────────────────────────────
            "overall": [
                {"$group": {
                    "_id": None,
                    "sessions": {"$addToSet": {"u": "$user_pseudo_id", "s": "$ga_session_id"}},
                    "users": {"$addToSet": "$user_pseudo_id"},
                    "revenue": {"$sum": "$revenue"},
                    "transactions": {"$addToSet": "$transaction_id_clean"},
                }},
                {"$project": {
                    "_id": 0,
                    "session_count": {"$size": "$sessions"},
                    "user_count": {"$size": "$users"},
                    "revenue": 1,
                    "transaction_count": {
                        "$size": {
                            "$filter": {
                                "input": "$transactions",
                                "cond": {"$ne": ["$$this", None]},
                            }
                        }
                    },
                }},
            ],
            # ── Daily breakdown ─────────────────────────────────────────────
            "daily": [
                {"$group": {
                    "_id": "$event_date",
                    "sessions": {"$addToSet": {"u": "$user_pseudo_id", "s": "$ga_session_id"}},
                    "revenue": {"$sum": "$revenue"},
                    "transactions": {"$addToSet": "$transaction_id_clean"},
                }},
                {"$project": {
                    "date": "$_id",
                    "_id": 0,
                    "session_count": {"$size": "$sessions"},
                    "revenue": 1,
                    "transaction_count": {
                        "$size": {
                            "$filter": {
                                "input": "$transactions",
                                "cond": {"$ne": ["$$this", None]},
                            }
                        }
                    },
                }},
                {"$sort": {"date": 1}},
            ],
            # ── By traffic source ───────────────────────────────────────────
            "by_source": [
                {"$group": {
                    "_id": "$traffic_source.source",
                    "sessions": {"$addToSet": {"u": "$user_pseudo_id", "s": "$ga_session_id"}},
                    "revenue": {"$sum": "$revenue"},
                    "transactions": {"$addToSet": "$transaction_id_clean"},
                }},
                {"$project": {
                    "source": {"$ifNull": ["$_id", "unknown"]},
                    "_id": 0,
                    "session_count": {"$size": "$sessions"},
                    "revenue": 1,
                    "transaction_count": {
                        "$size": {
                            "$filter": {
                                "input": "$transactions",
                                "cond": {"$ne": ["$$this", None]},
                            }
                        }
                    },
                }},
                {"$sort": {"session_count": -1}},
            ],
            # ── By device category ──────────────────────────────────────────
            "by_device": [
                {"$group": {
                    "_id": "$device.category",
                    "sessions": {"$addToSet": {"u": "$user_pseudo_id", "s": "$ga_session_id"}},
                    "revenue": {"$sum": "$revenue"},
                    "transactions": {"$addToSet": "$transaction_id_clean"},
                }},
                {"$project": {
                    "device": {"$ifNull": ["$_id", "unknown"]},
                    "_id": 0,
                    "session_count": {"$size": "$sessions"},
                    "revenue": 1,
                    "transaction_count": {
                        "$size": {
                            "$filter": {
                                "input": "$transactions",
                                "cond": {"$ne": ["$$this", None]},
                            }
                        }
                    },
                }},
                {"$sort": {"session_count": -1}},
            ],
            # ── Bounce sessions (1 event per session) ───────────────────────
            "bounce": [
                {"$group": {
                    "_id": {"u": "$user_pseudo_id", "s": "$ga_session_id"},
                    "event_count": {"$sum": 1},
                }},
                {"$match": {"event_count": 1}},
                {"$count": "bounce_count"},
            ],
            # ── By country (geo) ────────────────────────────────────────────
            "by_geo": [
                {"$group": {
                    "_id": {"$ifNull": ["$geo.country", "unknown"]},
                    "sessions": {"$addToSet": {"u": "$user_pseudo_id", "s": "$ga_session_id"}},
                    "revenue": {"$sum": "$revenue"},
                    "transactions": {"$addToSet": "$transaction_id_clean"},
                }},
                {"$project": {
                    "country": {"$ifNull": ["$_id", "unknown"]},
                    "_id": 0,
                    "session_count": {"$size": "$sessions"},
                    "revenue": 1,
                    "transaction_count": {
                        "$size": {
                            "$filter": {
                                "input": "$transactions",
                                "cond": {"$ne": ["$$this", None]},
                            }
                        }
                    },
                }},
                {"$sort": {"session_count": -1}},
                {"$limit": 8},
            ],
            # ── New users (first_visit event) ────────────────────────────────
            "new_users": [
                {"$match": {"event_name": "first_visit"}},
                {"$group": {"_id": None, "ids": {"$addToSet": "$user_pseudo_id"}}},
                {"$project": {"_id": 0, "count": {"$size": "$ids"}}},
            ],
        }},
    ]

    docs = await col.aggregate(pipeline).to_list(length=None)
    return docs[0] if docs else {}


async def _aggregate_by_category(items_col, start: str, end: str) -> list[dict]:
    """Aggregate item category breakdown from event_items collection."""
    pipeline = [
        {"$match": {
            "event_date": {"$gte": start, "$lte": end},
            "event_name": {"$in": ["view_item", "add_to_cart", "purchase"]},
        }},
        {"$group": {
            "_id": {"$ifNull": ["$item_category", "unknown"]},
            "view_count": {"$sum": {"$cond": [{"$eq": ["$event_name", "view_item"]}, 1, 0]}},
            "add_to_cart_count": {"$sum": {"$cond": [{"$eq": ["$event_name", "add_to_cart"]}, 1, 0]}},
            "purchase_count": {"$sum": {"$cond": [{"$eq": ["$event_name", "purchase"]}, 1, 0]}},
            "revenue": {"$sum": {
                "$cond": [
                    {"$eq": ["$event_name", "purchase"]},
                    {"$multiply": [
                        {"$ifNull": ["$price", 0]},
                        {"$ifNull": ["$quantity", 1]},
                    ]},
                    0,
                ]
            }},
        }},
        {"$project": {
            "category": "$_id",
            "_id": 0,
            "view_count": 1,
            "add_to_cart_count": 1,
            "purchase_count": 1,
            "revenue": 1,
        }},
        {"$sort": {"revenue": -1}},
    ]
    return await items_col.aggregate(pipeline).to_list(length=None)


def _extract_kpis(facet: dict) -> dict:
    overall = (facet.get("overall") or [{}])[0]
    session_count = overall.get("session_count", 0)
    transaction_count = overall.get("transaction_count", 0)
    total_revenue = round(overall.get("revenue", 0.0), 2)
    user_count = overall.get("user_count", 0)
    bounce_count = (facet.get("bounce") or [{}])[0].get("bounce_count", 0)

    arpu = round(total_revenue / transaction_count, 2) if transaction_count > 0 else 0.0
    cvr = round(transaction_count / session_count, 4) if session_count > 0 else 0.0
    bounce_rate = round(bounce_count / session_count, 4) if session_count > 0 else 0.0

    return {
        "total_revenue": total_revenue,
        "transaction_count": transaction_count,
        "arpu": arpu,
        "session_count": session_count,
        "user_count": user_count,
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
            "week_start/week_end 범위 확인 필요"
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
        logger.info("performance_agent: week_start=%r  week_end=%r", week_start, week_end)
        col = get_collection("raw_logs")
        items_col = get_collection("event_items")

        facet = await _aggregate_week(col, week_start, week_end)
        kpis = _extract_kpis(facet)

        daily_breakdown = [
            {
                "date": d["date"],
                "revenue": round(d.get("revenue", 0.0), 2),
                "transaction_count": d.get("transaction_count", 0),
                "session_count": d.get("session_count", 0),
            }
            for d in (facet.get("daily") or [])
        ]

        by_traffic_source = [
            {
                "source": d.get("source", "unknown"),
                "session_count": d.get("session_count", 0),
                "transaction_count": d.get("transaction_count", 0),
                "revenue": round(d.get("revenue", 0.0), 2),
                "conversion_rate": round(
                    d.get("transaction_count", 0) / d["session_count"], 4
                ) if d.get("session_count", 0) > 0 else 0.0,
            }
            for d in (facet.get("by_source") or [])
        ]

        by_device_category = [
            {
                "device": d.get("device", "unknown"),
                "session_count": d.get("session_count", 0),
                "transaction_count": d.get("transaction_count", 0),
                "revenue": round(d.get("revenue", 0.0), 2),
                "conversion_rate": round(
                    d.get("transaction_count", 0) / d["session_count"], 4
                ) if d.get("session_count", 0) > 0 else 0.0,
            }
            for d in (facet.get("by_device") or [])
        ]

        raw_by_category = await _aggregate_by_category(items_col, week_start, week_end)
        by_item_category = [
            {
                "category": d.get("category", "unknown"),
                "view_count": d.get("view_count", 0),
                "add_to_cart_count": d.get("add_to_cart_count", 0),
                "purchase_count": d.get("purchase_count", 0),
                "revenue": round(d.get("revenue", 0.0), 2),
                # None when view_count < 10 (insufficient data) — PPT renders as "N/A"
                "purchase_rate": round(
                    d.get("purchase_count", 0) / d["view_count"], 4
                ) if d.get("view_count", 0) >= 10 else None,
            }
            for d in raw_by_category
        ]

        by_geo = [
            {
                "country": d.get("country", "unknown"),
                "session_count": d.get("session_count", 0),
                "transaction_count": d.get("transaction_count", 0),
                "revenue": round(d.get("revenue", 0.0), 2),
                "conversion_rate": round(
                    d.get("transaction_count", 0) / d["session_count"], 4
                ) if d.get("session_count", 0) > 0 else 0.0,
            }
            for d in (facet.get("by_geo") or [])
        ]

        new_user_count = (facet.get("new_users") or [{}])[0].get("count", 0)
        total_user_count = kpis.get("user_count", 0)
        new_vs_returning = {
            "new_users": new_user_count,
            "returning_users": max(total_user_count - new_user_count, 0),
            "total_users": total_user_count,
        }

        # ── WoW ───────────────────────────────────────────────────────────────
        prior_start = shift_days(week_start, -7)
        prior_end = shift_days(week_end, -7)
        prior_facet = await _aggregate_week(col, prior_start, prior_end)
        prior_kpis = _extract_kpis(prior_facet)

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
            "by_geo": by_geo,
            "new_vs_returning": new_vs_returning,
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

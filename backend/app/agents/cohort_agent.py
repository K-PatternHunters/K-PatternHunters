"""Cohort Analysis Agent — first-purchase cohort retention and revenue tracking.

Input  (PipelineState keys consumed):
    week_start     : str  — "YYYYMMDD"  (used only for domain_context; cohort uses full history)
    week_end       : str  — "YYYYMMDD"
    domain_context : dict — DomainContext.model_dump()

Output (PipelineState keys produced):
    cohort_metrics : dict
"""

from __future__ import annotations

import logging
from collections import defaultdict

from pydantic import ValidationError

from app.agents._ga4_utils import PREPROCESS_STAGE, date_to_iso_week, week_offset
from app.agents._agent_utils import error_patch, validate_or_retry
from app.core.models import CohortMetrics
from app.db.mongo import get_collection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cohort computation (pure Python — runs on aggregation results)
# ---------------------------------------------------------------------------

def _build_cohorts(purchase_docs: list[dict]) -> list[dict]:
    """
    purchase_docs: [{"user_pseudo_id": str, "first_purchase_date": str, "purchases": [{"date": str, "revenue": float}]}]
    """
    first_purchase_week: dict[str, str] = {}
    purchases: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for doc in purchase_docs:
        uid = doc.get("user_pseudo_id") or doc.get("_id", "")
        first_date = doc.get("first_purchase_date", "")
        if not uid or not first_date:
            continue
        first_purchase_week[uid] = date_to_iso_week(first_date)
        for p in doc.get("purchases", []):
            iso_week = date_to_iso_week(p["date"])
            purchases[uid][iso_week] += p.get("revenue", 0.0)

    # Group users by cohort week
    cohort_users: dict[str, list[str]] = defaultdict(list)
    for uid, week in first_purchase_week.items():
        cohort_users[week].append(uid)

    all_weeks: set[str] = set()
    for uid_weeks in purchases.values():
        all_weeks.update(uid_weeks.keys())

    cohorts = []
    for cohort_week in sorted(cohort_users.keys()):
        users = cohort_users[cohort_week]
        cohort_size = len(users)
        relevant_weeks = sorted(
            (w for w in all_weeks
             if week_offset(cohort_week, w) is not None and week_offset(cohort_week, w) >= 0),
            key=lambda w: week_offset(cohort_week, w),
        )

        weeks_data = []
        seen_offsets: set[int] = set()
        for w in relevant_weeks:
            offset = week_offset(cohort_week, w)
            if offset is None or offset in seen_offsets:
                continue
            seen_offsets.add(offset)
            retained = [u for u in users if purchases[u].get(w, 0) > 0]
            revenue = sum(purchases[u].get(w, 0.0) for u in users)
            # W0 is the cohort's own week — by definition all users are retained
            if offset == 0:
                retention = 1.0
            else:
                retention = round(len(retained) / cohort_size, 4) if cohort_size > 0 else 0.0
            weeks_data.append({
                "week_offset": offset,
                "retained_users": cohort_size if offset == 0 else len(retained),
                "retention_rate": retention,
                "revenue": round(revenue, 2),
                "revenue_per_user": round(revenue / cohort_size, 2) if cohort_size > 0 else 0.0,
            })

        cohorts.append({
            "cohort_week": cohort_week,
            "cohort_size": cohort_size,
            "weeks": weeks_data,
        })

    return cohorts


def _build_summary(cohorts: list[dict]) -> dict:
    if not cohorts:
        return {
            "avg_week1_retention": 0.0,
            "best_retention_cohort": None,
            "typical_churn_week": None,
            "new_buyer_trend": "stable",
        }

    week1_retentions = [
        w["retention_rate"]
        for c in cohorts
        for w in c["weeks"]
        if w["week_offset"] == 1
    ]
    avg_week1 = round(sum(week1_retentions) / len(week1_retentions), 4) if week1_retentions else 0.0

    best_cohort = None
    best_ret = -1.0
    for c in cohorts:
        for w in c["weeks"]:
            if w["week_offset"] == 1 and w["retention_rate"] > best_ret:
                best_ret = w["retention_rate"]
                best_cohort = c["cohort_week"]

    offset_drop: dict[int, list[float]] = defaultdict(list)
    for c in cohorts:
        prev_ret = 1.0
        for w in sorted(c["weeks"], key=lambda x: x["week_offset"]):
            if w["week_offset"] == 0:
                prev_ret = w["retention_rate"]
                continue
            drop = prev_ret - w["retention_rate"]
            offset_drop[w["week_offset"]].append(drop)
            prev_ret = w["retention_rate"]

    typical_churn_week = None
    if offset_drop:
        avg_drops = {k: sum(v) / len(v) for k, v in offset_drop.items()}
        typical_churn_week = max(avg_drops, key=lambda k: avg_drops[k])

    sizes = [c["cohort_size"] for c in cohorts]
    mid = len(sizes) // 2
    if mid > 0:
        first_half_avg = sum(sizes[:mid]) / mid
        second_half_avg = sum(sizes[mid:]) / (len(sizes) - mid)
        ratio = second_half_avg / first_half_avg if first_half_avg > 0 else 1.0
        trend = "increasing" if ratio > 1.05 else ("decreasing" if ratio < 0.95 else "stable")
    else:
        trend = "stable"

    return {
        "avg_week1_retention": avg_week1,
        "best_retention_cohort": best_cohort,
        "typical_churn_week": typical_churn_week,
        "new_buyer_trend": trend,
    }


# ---------------------------------------------------------------------------
# Business-logic validation
# ---------------------------------------------------------------------------

def _validate(metrics: dict) -> list[str]:
    errors: list[str] = []
    cohorts = metrics.get("cohorts", [])
    if not cohorts:
        errors.append(
            "cohorts 리스트가 비어 있음 — 해당 기간에 purchase 이벤트가 없거나 "
            "user_pseudo_id 매핑 실패"
        )
    return errors


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def cohort_agent(state: dict) -> dict:
    """LangGraph node: first-purchase cohort retention and revenue analysis."""
    domain_context: dict = state.get("domain_context", {})
    cohort_cfg: dict = domain_context.get("cohort_config", {})
    cohort_definition = cohort_cfg.get("cohort_basis", "first_purchase_week")

    async def _run(s: dict) -> tuple[dict, list[str]]:
        col = get_collection("raw_logs")

        # Fetch all purchase history — no date filter (cohort needs full history)
        pipeline = [
            {"$match": {
                "event_name": "purchase",
                "ecommerce.purchase_revenue_in_usd": {"$gt": 0},
            }},
            PREPROCESS_STAGE,
            {"$group": {
                "_id": "$user_pseudo_id",
                "first_purchase_date": {"$min": "$event_date"},
                "purchases": {"$push": {
                    "date": "$event_date",
                    "revenue": "$revenue",
                }},
            }},
        ]
        purchase_docs = await col.aggregate(pipeline).to_list(length=None)

        # Normalise _id → user_pseudo_id for downstream
        for doc in purchase_docs:
            doc["user_pseudo_id"] = doc.pop("_id", "")

        cohorts = _build_cohorts(purchase_docs)
        summary = _build_summary(cohorts)
        metrics = {
            "cohort_definition": cohort_definition,
            "cohorts": cohorts,
            "summary": summary,
        }
        return metrics, _validate(metrics)

    cohort_metrics, validation_errors = await validate_or_retry(
        run_fn=_run,
        state=state,
        agent_name="cohort_agent",
        state_key="cohort_metrics",
    )

    logger.info(
        "cohort_agent: %d cohorts built  avg_week1_retention=%.4f",
        len(cohort_metrics.get("cohorts", [])),
        (cohort_metrics.get("summary") or {}).get("avg_week1_retention", 0),
    )

    try:
        CohortMetrics(**cohort_metrics)
    except ValidationError as exc:
        logger.warning("cohort_agent: schema validation failed — %s", exc)

    return {"cohort_metrics": cohort_metrics, **error_patch("cohort_agent", validation_errors)}

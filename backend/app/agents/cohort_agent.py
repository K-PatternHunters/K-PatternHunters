"""Cohort Analysis Agent — first-purchase cohort retention and revenue tracking.

Input  (PipelineState keys consumed):
    week_start     : str        — "YYYYMMDD"
    week_end       : str        — "YYYYMMDD"
    field_mapping  : dict       — from schema_mapping_agent
    raw_logs       : list[dict] — weekly raw log records
    domain_context : dict       — DomainContext.model_dump()

Output (PipelineState keys produced):
    cohort_metrics : dict
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.agents._ga4_utils import date_to_iso_week, get_purchase_revenue, week_offset

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------

def _build_cohort_data(raw_logs: list[dict]) -> dict:
    """
    Returns:
        first_purchase_week[user] : str (ISO week of user's first purchase)
        purchases[user][iso_week] : float (total revenue that week)
    """
    purchase_events: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for doc in raw_logs:
        if doc.get("event_name") != "purchase":
            continue
        uid = doc.get("user_pseudo_id", "")
        if not uid:
            continue
        event_date = doc.get("event_date", "")
        revenue = get_purchase_revenue(doc)
        purchase_events[uid].append((event_date, revenue))

    first_purchase_week: dict[str, str] = {}
    purchases: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for uid, events in purchase_events.items():
        earliest_date = min(e[0] for e in events)
        first_purchase_week[uid] = date_to_iso_week(earliest_date)
        for date, revenue in events:
            iso_week = date_to_iso_week(date)
            purchases[uid][iso_week] += revenue

    return {"first_purchase_week": first_purchase_week, "purchases": purchases}


def _build_cohorts(cohort_data: dict) -> list[dict]:
    first_purchase_week = cohort_data["first_purchase_week"]
    purchases = cohort_data["purchases"]

    # Group users by cohort week
    cohort_users: dict[str, list[str]] = defaultdict(list)
    for uid, week in first_purchase_week.items():
        cohort_users[week].append(uid)

    # Collect all ISO weeks that appear in the data
    all_weeks: set[str] = set()
    for uid_weeks in purchases.values():
        all_weeks.update(uid_weeks.keys())

    cohorts = []
    for cohort_week in sorted(cohort_users.keys()):
        users = cohort_users[cohort_week]
        cohort_size = len(users)
        user_set = set(users)

        # Determine which weeks are >= cohort_week, sorted by numeric offset (not string)
        relevant_weeks = sorted(
            (w for w in all_weeks if week_offset(cohort_week, w) is not None and week_offset(cohort_week, w) >= 0),
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
            weeks_data.append({
                "week_offset": offset,
                "retained_users": len(retained),
                "retention_rate": round(len(retained) / cohort_size, 4) if cohort_size > 0 else 0.0,
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

    # avg week1 retention
    week1_retentions = [
        w["retention_rate"]
        for c in cohorts
        for w in c["weeks"]
        if w["week_offset"] == 1
    ]
    avg_week1 = round(sum(week1_retentions) / len(week1_retentions), 4) if week1_retentions else 0.0

    # best retention cohort (by week1 retention)
    best_cohort = None
    best_ret = -1.0
    for c in cohorts:
        for w in c["weeks"]:
            if w["week_offset"] == 1 and w["retention_rate"] > best_ret:
                best_ret = w["retention_rate"]
                best_cohort = c["cohort_week"]

    # typical churn week: offset with highest avg drop
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

    # new buyer trend: compare first half vs second half cohort sizes
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
# Agent entry point
# ---------------------------------------------------------------------------

async def cohort_agent(state: dict) -> dict:
    """LangGraph node: first-purchase cohort retention and revenue analysis."""
    raw_logs: list[dict] = state.get("raw_logs", [])
    domain_context: dict = state.get("domain_context", {})

    cohort_cfg: dict = domain_context.get("cohort_config", {})
    cohort_definition = cohort_cfg.get("cohort_basis", "first_purchase_week")

    cohort_data = _build_cohort_data(raw_logs)
    cohorts = _build_cohorts(cohort_data)
    summary = _build_summary(cohorts)

    cohort_metrics = {
        "cohort_definition": cohort_definition,
        "cohorts": cohorts,
        "summary": summary,
    }

    logger.info(
        "cohort_agent: %d cohorts built  avg_week1_retention=%.4f",
        len(cohorts),
        summary["avg_week1_retention"],
    )
    return {"cohort_metrics": cohort_metrics}

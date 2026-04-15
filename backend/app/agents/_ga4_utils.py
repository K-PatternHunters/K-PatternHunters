"""Shared GA4 raw log parsing utilities.

All agents import from here instead of duplicating field-extraction logic.
All functions are pure (no I/O, no side effects).
"""

from __future__ import annotations

from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# MongoDB aggregation — common preprocessing stage
# ---------------------------------------------------------------------------

# Insert as the first stage (after $match) in every agent's aggregation pipeline.
#
# What it does:
#   - "revenue": purchase_revenue_in_usd first, fallback to purchase_revenue, then 0
#   - "transaction_id_clean": normalise "(not set)" / "" / null → null
PREPROCESS_STAGE: dict = {
    "$addFields": {
        "revenue": {
            "$ifNull": [
                "$ecommerce.purchase_revenue_in_usd",
                {"$ifNull": ["$ecommerce.purchase_revenue", 0]},
            ]
        },
        "transaction_id_clean": {
            "$cond": [
                {"$in": ["$ecommerce.transaction_id", ["(not set)", "", None]]},
                None,
                "$ecommerce.transaction_id",
            ]
        },
    }
}


# ---------------------------------------------------------------------------
# event_params extraction
# ---------------------------------------------------------------------------

def get_event_param(event_params: list[dict], key: str) -> str | int | float | None:
    """Extract a typed value from a GA4 event_params array by key."""
    for param in event_params or []:
        if param.get("key") == key:
            v = param.get("value") or {}
            return (
                v.get("string_value")
                or v.get("int_value")
                or v.get("float_value")
                or v.get("double_value")
            )
    return None


def get_session_id(doc: dict) -> str | None:
    """Extract session_id from event_params (ga_session_id / session_id) or top-level."""
    for key in ("ga_session_id", "session_id"):
        v = get_event_param(doc.get("event_params", []), key)
        if v is not None:
            return str(v)
    return doc.get("session_id")


# ---------------------------------------------------------------------------
# Dimension extractors
# ---------------------------------------------------------------------------

def get_traffic_source(doc: dict) -> str:
    ts = doc.get("traffic_source") or {}
    src = ts.get("source")
    if src:
        return src
    return str(get_event_param(doc.get("event_params", []), "source") or "unknown")


def get_device_category(doc: dict) -> str:
    return (doc.get("device") or {}).get("category", "unknown")


# ---------------------------------------------------------------------------
# Ecommerce extractors
# ---------------------------------------------------------------------------

def get_purchase_revenue(doc: dict) -> float:
    ecommerce = doc.get("ecommerce") or {}
    revenue = ecommerce.get("purchase_revenue") or ecommerce.get("revenue") or 0.0
    try:
        return float(revenue)
    except (TypeError, ValueError):
        return 0.0


def get_transaction_id(doc: dict) -> str | None:
    return (doc.get("ecommerce") or {}).get("transaction_id")


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def in_range(event_date: str, start: str, end: str) -> bool:
    """Check if YYYYMMDD string is within [start, end] inclusive."""
    return start <= event_date <= end


def shift_days(date_str: str, days: int) -> str:
    """Return a YYYYMMDD string shifted by N days."""
    try:
        dt = datetime.strptime(date_str, "%Y%m%d") + timedelta(days=days)
        return dt.strftime("%Y%m%d")
    except ValueError:
        return date_str


def date_to_iso_week(date_str: str) -> str:
    """Convert YYYYMMDD to ISO week string e.g. '2021-W01'."""
    try:
        dt = datetime.strptime(date_str, "%Y%m%d")
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except ValueError:
        return "unknown"


def date_to_weekday(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y%m%d").strftime("%A")
    except ValueError:
        return "unknown"


def week_offset(cohort_week: str, event_week: str) -> int | None:
    """Number of ISO weeks between two 'YYYY-Www' strings. None if unparseable."""
    try:
        def _parse(s: str) -> datetime:
            year, w = s.split("-W")
            # Use ISO 8601 week parsing (%G=ISO year, %V=ISO week, %u=Mon=1)
            return datetime.strptime(f"{year}-W{int(w):02d}-1", "%G-W%V-%u")
        return (_parse(event_week) - _parse(cohort_week)).days // 7
    except (ValueError, AttributeError):
        return None

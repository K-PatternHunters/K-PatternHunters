"""Anomaly Detection Agent — Z-score based detection + LLM interpretation.

Input  (PipelineState keys consumed):
    week_start     : str        — "YYYYMMDD"
    week_end       : str        — "YYYYMMDD"
    field_mapping  : dict       — from schema_mapping_agent
    raw_logs       : list[dict] — weekly raw log records (includes lookback weeks)
    domain_context : dict       — DomainContext.model_dump()

Output (PipelineState keys produced):
    anomaly_metrics : dict
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

from pydantic import ValidationError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.models import AnomalyMetrics
from app.agents._ga4_utils import (
    date_to_weekday,
    get_purchase_revenue,
    get_session_id,
    get_transaction_id,
    in_range,
    shift_days,
)

logger = logging.getLogger(__name__)

_LOOKBACK_WEEKS = 4
_MIN_BASELINE_DAYS = 7

_LLM_SYSTEM_PROMPT = """\
You are a data analytics expert. Given a single anomalous data point from a web analytics metric,
write a 1-2 sentence interpretation in Korean explaining the most likely business cause or meaning.
Be concise and actionable. Focus on possible causes, not just the numbers."""


# ---------------------------------------------------------------------------
# Daily metric aggregation
# ---------------------------------------------------------------------------

def _aggregate_daily(raw_logs: list[dict], start: str, end: str) -> dict[str, dict]:
    """Return {date: {daily_revenue, daily_session_count, daily_conversion_rate}}."""
    daily_revenue: dict[str, float] = defaultdict(float)
    daily_sessions: dict[str, set] = defaultdict(set)
    daily_transactions: dict[str, set] = defaultdict(set)

    for doc in raw_logs:
        event_date = doc.get("event_date", "")
        if not in_range(event_date, start, end):
            continue
        sid = get_session_id(doc)
        if sid:
            daily_sessions[event_date].add(sid)
        if doc.get("event_name") == "purchase":
            daily_revenue[event_date] += get_purchase_revenue(doc)
            txn = get_transaction_id(doc)
            if txn:
                daily_transactions[event_date].add(txn)

    all_dates = set(daily_sessions) | set(daily_revenue)
    result: dict[str, dict] = {}
    for d in all_dates:
        sc = len(daily_sessions[d])
        tc = len(daily_transactions[d])
        result[d] = {
            "daily_revenue": round(daily_revenue[d], 2),
            "daily_session_count": sc,
            "daily_conversion_rate": round(tc / sc, 6) if sc > 0 else 0.0,
        }
    return result


# ---------------------------------------------------------------------------
# Z-score computation
# ---------------------------------------------------------------------------

def _mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return mean, math.sqrt(variance)


def _detect_anomalies(
    current_daily: dict[str, dict],
    baseline_daily: dict[str, dict],
    target_metrics: list[str],
    threshold: float,
) -> tuple[list[dict], list[dict]]:
    anomalies: list[dict] = []
    clean: list[dict] = []

    for metric in target_metrics:
        baseline_values = [v[metric] for v in baseline_daily.values() if metric in v]
        if len(baseline_values) < 2:
            logger.warning("anomaly_agent: not enough baseline data for metric=%s", metric)
            continue

        mean, std = _mean_std(baseline_values)
        if std == 0.0:
            logger.info("anomaly_agent: std=0 for metric=%s — skipping", metric)
            continue

        metric_max_z = 0.0
        for date in sorted(current_daily.keys()):
            observed = current_daily[date].get(metric)
            if observed is None:
                continue
            z = (observed - mean) / std
            metric_max_z = max(metric_max_z, abs(z))

            if abs(z) >= threshold:
                anomalies.append({
                    "metric": metric,
                    "date": date,
                    "observed_value": observed,
                    "expected_mean": round(mean, 6),
                    "expected_std": round(std, 6),
                    "z_score": round(z, 4),
                    "direction": "high" if z > 0 else "low",
                    "llm_interpretation": None,  # filled later
                })

        clean.append({"metric": metric, "max_z_score": round(metric_max_z, 4), "status": "normal"})

    return anomalies, clean


# ---------------------------------------------------------------------------
# LLM interpretation
# ---------------------------------------------------------------------------

async def _interpret_anomalies(anomalies: list[dict], domain: str) -> list[dict]:
    if not anomalies:
        return anomalies

    settings = get_settings()
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=settings.OPENAI_API_KEY)

    for anomaly in anomalies:
        weekday = date_to_weekday(anomaly["date"])
        human = (
            f"도메인: {domain}\n"
            f"지표: {anomaly['metric']}\n"
            f"날짜: {anomaly['date']} ({weekday})\n"
            f"관측값: {anomaly['observed_value']}\n"
            f"기대값(평균): {anomaly['expected_mean']}\n"
            f"Z-score: {anomaly['z_score']} ({anomaly['direction']})\n"
        )
        try:
            response = await llm.ainvoke(
                [SystemMessage(content=_LLM_SYSTEM_PROMPT), HumanMessage(content=human)]
            )
            anomaly["llm_interpretation"] = response.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("anomaly_agent: LLM interpretation failed: %s", exc)
            anomaly["llm_interpretation"] = None

    return anomalies


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def anomaly_agent(state: dict) -> dict:
    """LangGraph node: Z-score anomaly detection + LLM interpretation."""
    week_start: str = state.get("week_start", "")
    week_end: str = state.get("week_end", "")
    raw_logs: list[dict] = state.get("raw_logs", [])
    domain_context: dict = state.get("domain_context", {})

    anomaly_cfg: dict = domain_context.get("anomaly_config", {})
    target_metrics: list[str] = anomaly_cfg.get("target_metrics", [
        "daily_revenue", "daily_session_count", "daily_conversion_rate"
    ])
    threshold: float = float(anomaly_cfg.get("threshold", 2.0))
    domain: str = domain_context.get("domain", "ecommerce")

    # Baseline: lookback _LOOKBACK_WEEKS weeks before current week
    baseline_start = shift_days(week_start, -7 * _LOOKBACK_WEEKS)
    baseline_end = shift_days(week_start, -1)

    current_daily = _aggregate_daily(raw_logs, week_start, week_end)
    baseline_daily = _aggregate_daily(raw_logs, baseline_start, baseline_end)

    if len(baseline_daily) < _MIN_BASELINE_DAYS:
        logger.warning(
            "anomaly_agent: only %d baseline days available (need %d) — using all available",
            len(baseline_daily),
            _MIN_BASELINE_DAYS,
        )

    anomalies, clean_metrics = _detect_anomalies(current_daily, baseline_daily, target_metrics, threshold)

    # LLM interpretation only when anomalies exist
    if anomalies:
        anomalies = await _interpret_anomalies(anomalies, domain)

    affected_metrics = list({a["metric"] for a in anomalies})
    most_abnormal_date = (
        max(anomalies, key=lambda a: abs(a["z_score"]))["date"] if anomalies else None
    )

    anomaly_metrics = {
        "method": anomaly_cfg.get("method", "z_score"),
        "threshold": threshold,
        "lookback_weeks": _LOOKBACK_WEEKS,
        "anomalies": anomalies,
        "clean_metrics": clean_metrics,
        "summary": {
            "total_anomalies": len(anomalies),
            "affected_metrics": affected_metrics,
            "most_abnormal_date": most_abnormal_date,
        },
    }

    logger.info(
        "anomaly_agent: total_anomalies=%d  affected_metrics=%s",
        len(anomalies),
        affected_metrics,
    )

    try:
        AnomalyMetrics(**anomaly_metrics)
    except ValidationError as exc:
        logger.warning("anomaly_agent: output validation failed — %s", exc)

    return {"anomaly_metrics": anomaly_metrics}

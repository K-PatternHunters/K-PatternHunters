"""Anomaly Detection Agent — Z-score based detection + LLM interpretation.

Input  (PipelineState keys consumed):
    week_start     : str  — "YYYYMMDD"
    week_end       : str  — "YYYYMMDD"
    domain_context : dict — DomainContext.model_dump()

Output (PipelineState keys produced):
    anomaly_metrics : dict
"""

from __future__ import annotations

import logging
import math

from pydantic import ValidationError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.models import AnomalyMetrics
from app.agents._ga4_utils import PREPROCESS_STAGE, date_to_weekday, shift_days
from app.db.mongo import get_collection

logger = logging.getLogger(__name__)

_LOOKBACK_WEEKS = 4
_LOOKBACK_WEEKS_MAX = 26   # fallback when primary baseline is insufficient
_MIN_BASELINE_DAYS = 7

_LLM_SYSTEM_PROMPT = """\
You are a data analytics expert. Given a single anomalous data point from a web analytics metric,
write a 1-2 sentence interpretation in Korean explaining the most likely business cause or meaning.
Be concise and actionable. Focus on possible causes, not just the numbers."""


# ---------------------------------------------------------------------------
# MongoDB aggregation — daily metrics
# ---------------------------------------------------------------------------

async def _aggregate_daily(col, start: str, end: str) -> dict[str, dict]:
    """Return {date: {daily_revenue, daily_session_count, daily_conversion_rate}}."""
    pipeline = [
        {"$match": {"event_date": {"$gte": start, "$lte": end}}},
        PREPROCESS_STAGE,
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
    ]
    docs = await col.aggregate(pipeline).to_list(length=None)

    result: dict[str, dict] = {}
    for d in docs:
        sc = d.get("session_count", 0)
        tc = d.get("transaction_count", 0)
        result[d["date"]] = {
            "daily_revenue": round(d.get("revenue", 0.0), 2),
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
                    "llm_interpretation": None,
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
    domain_context: dict = state.get("domain_context", {})

    anomaly_cfg: dict = domain_context.get("anomaly_config", {})
    target_metrics: list[str] = anomaly_cfg.get("target_metrics", [
        "daily_revenue", "daily_session_count", "daily_conversion_rate"
    ])
    threshold: float = float(anomaly_cfg.get("threshold", 2.0))
    domain: str = domain_context.get("domain", "ecommerce")

    baseline_start = shift_days(week_start, -7 * _LOOKBACK_WEEKS)
    baseline_end = shift_days(week_start, -1)

    col = get_collection("raw_logs")
    current_daily = await _aggregate_daily(col, week_start, week_end)
    baseline_daily = await _aggregate_daily(col, baseline_start, baseline_end)

    if len(baseline_daily) < _MIN_BASELINE_DAYS:
        # Primary baseline (4 weeks) is insufficient — extend to up to 26 weeks
        extended_start = shift_days(week_start, -7 * _LOOKBACK_WEEKS_MAX)
        extended_daily = await _aggregate_daily(col, extended_start, baseline_end)
        if len(extended_daily) > len(baseline_daily):
            logger.info(
                "anomaly_agent: extended baseline from %d to %d days (start=%s)",
                len(baseline_daily), len(extended_daily), extended_start,
            )
            baseline_daily = extended_daily
            baseline_start = extended_start
        else:
            logger.warning(
                "anomaly_agent: only %d baseline days available even after extending to %d weeks",
                len(baseline_daily),
                _LOOKBACK_WEEKS_MAX,
            )

    anomalies, clean_metrics = _detect_anomalies(current_daily, baseline_daily, target_metrics, threshold)

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
            "baseline_days_available": len(baseline_daily),
            "baseline_start": baseline_start,
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

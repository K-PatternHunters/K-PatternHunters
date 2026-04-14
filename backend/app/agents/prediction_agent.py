"""Prediction Agent — linear trend forecast for next-week KPIs + LLM comment.

Input  (PipelineState keys consumed):
    week_start     : str        — "YYYYMMDD"
    week_end       : str        — "YYYYMMDD"
    field_mapping  : dict       — from schema_mapping_agent
    raw_logs       : list[dict] — weekly raw log records (includes lookback weeks)
    domain_context : dict       — DomainContext.model_dump()

Output (PipelineState keys produced):
    prediction_metrics : dict
"""

from __future__ import annotations

import logging

from pydantic import ValidationError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.models import PredictionMetrics
from app.agents._agent_utils import error_patch, validate_or_retry
from app.agents._ga4_utils import (
    date_to_iso_week,
    get_purchase_revenue,
    get_transaction_id,
    in_range,
    shift_days,
)

logger = logging.getLogger(__name__)

_LLM_SYSTEM_PROMPT = """\
You are a data analytics expert. Given a weekly trend forecast for a single business metric,
write a 1-2 sentence commentary in Korean that explains the trend direction and what the
prediction means for the business. Be concise and mention the predicted value and confidence interval."""


# ---------------------------------------------------------------------------
# Weekly aggregation
# ---------------------------------------------------------------------------

def _aggregate_week(raw_logs: list[dict], start: str, end: str) -> dict:
    revenue = 0.0
    transaction_ids: set[str] = set()
    for doc in raw_logs:
        event_date = doc.get("event_date", "")
        if not in_range(event_date, start, end):
            continue
        if doc.get("event_name") == "purchase":
            revenue += get_purchase_revenue(doc)
            txn = get_transaction_id(doc)
            if txn:
                transaction_ids.add(txn)
    return {
        "next_week_revenue": round(revenue, 2),
        "next_week_transaction_count": len(transaction_ids),
    }


# ---------------------------------------------------------------------------
# Linear trend (pure Python least-squares)
# ---------------------------------------------------------------------------

def _linear_least_squares(y: list[float]) -> tuple[float, float]:
    """Returns (slope, intercept) for x = [0, 1, ..., n-1]."""
    n = len(y)
    if n < 2:
        return 0.0, y[0] if y else 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(y) / n
    ss_xx = sum((i - x_mean) ** 2 for i in range(n))
    ss_xy = sum((i - x_mean) * (yi - y_mean) for i, yi in enumerate(y))
    slope = ss_xy / ss_xx if ss_xx != 0 else 0.0
    intercept = y_mean - slope * x_mean
    return slope, intercept


def _residual_std(y: list[float], slope: float, intercept: float) -> float:
    n = len(y)
    if n < 2:
        return 0.0
    fitted = [slope * i + intercept for i in range(n)]
    residuals = [yi - fi for yi, fi in zip(y, fitted)]
    variance = sum(r ** 2 for r in residuals) / n
    import math  # noqa: PLC0415
    return math.sqrt(variance)


def _trend_direction(slope: float, y: list[float]) -> str:
    if not y:
        return "stable"
    mean_val = sum(y) / len(y)
    if mean_val == 0:
        return "stable"
    relative = abs(slope) / mean_val
    if relative < 0.05:
        return "stable"
    return "increasing" if slope > 0 else "decreasing"


def _forecast(target: str, historical: list[dict], lookback: int) -> dict:
    """Compute prediction for a single target metric."""
    values = [h["value"] for h in historical]
    n = len(values)

    if n < 2:
        return {
            "target": target,
            "historical": historical,
            "predicted_value": values[0] if values else 0.0,
            "confidence_interval": {"lower": 0.0, "upper": 0.0},
            "trend_direction": "stable",
            "trend_slope": 0.0,
            "llm_comment": None,
            "skipped": True,
        }

    slope, intercept = _linear_least_squares(values)
    predicted = max(0.0, slope * n + intercept)
    res_std = _residual_std(values, slope, intercept)
    margin = 1.96 * res_std

    return {
        "target": target,
        "historical": historical,
        "predicted_value": round(predicted, 2),
        "confidence_interval": {
            "lower": round(max(0.0, predicted - margin), 2),
            "upper": round(predicted + margin, 2),
        },
        "trend_direction": _trend_direction(slope, values),
        "trend_slope": round(slope, 4),
        "llm_comment": None,
        "skipped": False,
    }


# ---------------------------------------------------------------------------
# LLM comment
# ---------------------------------------------------------------------------

async def _add_llm_comments(predictions: list[dict], domain: str) -> list[dict]:
    settings = get_settings()
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=settings.OPENAI_API_KEY)

    for pred in predictions:
        if pred.get("skipped"):
            continue
        human = (
            f"도메인: {domain}\n"
            f"지표: {pred['target']}\n"
            f"과거 데이터: {[h['value'] for h in pred['historical']]}\n"
            f"예측값: {pred['predicted_value']}\n"
            f"신뢰구간: {pred['confidence_interval']['lower']} ~ {pred['confidence_interval']['upper']}\n"
            f"추세: {pred['trend_direction']} (slope={pred['trend_slope']})\n"
        )
        try:
            response = await llm.ainvoke(
                [SystemMessage(content=_LLM_SYSTEM_PROMPT), HumanMessage(content=human)]
            )
            pred["llm_comment"] = response.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("prediction_agent: LLM comment failed: %s", exc)

    return predictions


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Business-logic validation
# ---------------------------------------------------------------------------

def _validate(metrics: dict) -> list[str]:
    errors: list[str] = []
    predictions = metrics.get("predictions", [])
    if predictions and all(p.get("skipped") for p in predictions):
        errors.append(
            "모든 prediction target이 skipped 처리됨 — "
            "lookback 기간 내 non-zero 데이터가 2주 미만, raw_logs 범위 확인 필요"
        )
    return errors


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def prediction_agent(state: dict) -> dict:
    """LangGraph node: linear trend forecast for next-week metrics."""
    domain_context: dict = state.get("domain_context", {})
    pred_cfg: dict = domain_context.get("prediction_config", {})
    targets: list[str] = pred_cfg.get("targets", [
        "next_week_revenue", "next_week_transaction_count"
    ])
    lookback_weeks: int = int(pred_cfg.get("lookback_weeks", 4))
    domain: str = domain_context.get("domain", "ecommerce")

    async def _run(s: dict) -> tuple[dict, list[str]]:
        week_start: str = s.get("week_start", "")
        week_end: str = s.get("week_end", "")
        raw_logs: list[dict] = s.get("raw_logs", [])

        weekly_data: list[dict] = []
        for i in range(lookback_weeks - 1, -1, -1):
            w_start = shift_days(week_start, -7 * i)
            w_end = shift_days(week_end, -7 * i)
            agg = _aggregate_week(raw_logs, w_start, w_end)
            iso_week = date_to_iso_week(w_start)
            weekly_data.append({"iso_week": iso_week, "w_start": w_start, "agg": agg})

        data_quality_warning = None
        actual_weeks = sum(
            1 for w in weekly_data
            if w["agg"]["next_week_revenue"] > 0 or w["agg"]["next_week_transaction_count"] > 0
        )
        if actual_weeks < lookback_weeks:
            data_quality_warning = f"Only {actual_weeks} weeks of data available (requested {lookback_weeks})"

        predictions = []
        for target in targets:
            historical = [
                {"week": w["iso_week"], "value": w["agg"].get(target, 0.0)}
                for w in weekly_data
            ]
            non_zero = [h for h in historical if h["value"] > 0]
            if len(non_zero) < 2:
                predictions.append({
                    "target": target,
                    "historical": historical,
                    "predicted_value": 0.0,
                    "confidence_interval": {"lower": 0.0, "upper": 0.0},
                    "trend_direction": "stable",
                    "trend_slope": 0.0,
                    "llm_comment": None,
                    "skipped": True,
                })
                continue
            predictions.append(_forecast(target, historical, lookback_weeks))

        predictions = await _add_llm_comments(predictions, domain)

        trend_directions = [p["trend_direction"] for p in predictions if not p.get("skipped")]
        overall = max(set(trend_directions), key=trend_directions.count) if trend_directions else "stable"

        metrics = {
            "method": pred_cfg.get("method", "linear_trend"),
            "lookback_weeks": lookback_weeks,
            "predictions": predictions,
            "summary": {
                "overall_trend": overall,
                "data_quality_warning": data_quality_warning,
            },
        }
        return metrics, _validate(metrics)

    prediction_metrics, validation_errors = await validate_or_retry(
        run_fn=_run,
        state=state,
        agent_name="prediction_agent",
        state_key="prediction_metrics",
    )

    logger.info(
        "prediction_agent: %d targets  overall_trend=%s",
        len(prediction_metrics.get("predictions", [])),
        (prediction_metrics.get("summary") or {}).get("overall_trend", "stable"),
    )

    try:
        PredictionMetrics(**prediction_metrics)
    except ValidationError as exc:
        logger.warning("prediction_agent: schema validation failed — %s", exc)

    return {"prediction_metrics": prediction_metrics, **error_patch("prediction_agent", validation_errors)}

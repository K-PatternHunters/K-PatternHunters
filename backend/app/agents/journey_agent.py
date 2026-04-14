"""Journey & Flow Analysis Agent — session event sequences, top paths, transition matrix.

Input  (PipelineState keys consumed):
    week_start     : str  — "YYYYMMDD"
    week_end       : str  — "YYYYMMDD"
    domain_context : dict — DomainContext.model_dump()

Output (PipelineState keys produced):
    journey_metrics : dict
"""

from __future__ import annotations

import logging
from collections import defaultdict

from pydantic import ValidationError

from app.agents._ga4_utils import PREPROCESS_STAGE
from app.agents._agent_utils import error_patch, validate_or_retry
from app.core.models import JourneyMetrics
from app.db.mongo import get_collection

logger = logging.getLogger(__name__)


def _is_converted(path: list[str], exit_events: list[str]) -> bool:
    return any(e in path for e in exit_events if e != "session_end")


# ---------------------------------------------------------------------------
# Pure Python post-processing (runs on aggregation results)
# ---------------------------------------------------------------------------

def _build_path_stats(
    sessions: list[dict],
    exit_events: list[str],
    top_n: int,
) -> tuple[list[dict], list[dict]]:
    converted_counts: dict[tuple, int] = defaultdict(int)
    churned_counts: dict[tuple, int] = defaultdict(int)

    for s in sessions:
        path_tuple = tuple(s["path"])
        if _is_converted(s["path"], exit_events):
            converted_counts[path_tuple] += 1
        else:
            churned_counts[path_tuple] += 1

    total_converted = sum(converted_counts.values())
    total_churned = sum(churned_counts.values())

    def top_n_paths(counts: dict, total: int) -> list[dict]:
        sorted_paths = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [
            {
                "path": list(path),
                "session_count": cnt,
                "ratio": round(cnt / total, 4) if total > 0 else 0.0,
            }
            for path, cnt in sorted_paths
        ]

    return top_n_paths(converted_counts, total_converted), top_n_paths(churned_counts, total_churned)


def _build_transition_matrix(sessions: list[dict], top_n_nodes: int = 20) -> dict[str, dict[str, float]]:
    pair_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    event_counts: dict[str, int] = defaultdict(int)

    for s in sessions:
        path = s["path"]
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            pair_counts[a][b] += 1
            event_counts[a] += 1

    top_events = sorted(event_counts, key=lambda e: event_counts[e], reverse=True)[:top_n_nodes]
    top_set = set(top_events)

    matrix: dict[str, dict[str, float]] = {}
    for a in top_events:
        total = event_counts[a]
        if total == 0:
            continue
        matrix[a] = {
            b: round(cnt / total, 4)
            for b, cnt in pair_counts[a].items()
            if b in top_set
        }
    return matrix


def _pre_churn_pattern(churned_paths: list[dict]) -> str:
    pair_counts: dict[str, int] = defaultdict(int)
    for item in churned_paths:
        path = item["path"]
        if len(path) >= 2:
            pair_counts[f"{path[-2]} → {path[-1]}"] += item["session_count"]
    if not pair_counts:
        return ""
    return max(pair_counts, key=lambda k: pair_counts[k])


# ---------------------------------------------------------------------------
# Business-logic validation
# ---------------------------------------------------------------------------

def _validate(metrics: dict) -> list[str]:
    errors: list[str] = []
    summary = metrics.get("summary", {})
    if summary.get("total_sessions", 0) == 0:
        errors.append(
            "total_sessions == 0 — 해당 기간에 session_id를 가진 이벤트가 없음, "
            "week_start/week_end 범위 확인 필요"
        )
    return errors


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

async def journey_agent(state: dict) -> dict:
    """LangGraph node: session journey paths, transition matrix, pre-churn pattern."""
    domain_context: dict = state.get("domain_context", {})
    journey_cfg: dict = domain_context.get("journey_config", {})
    top_n: int = journey_cfg.get("top_n", 10)
    max_depth: int = journey_cfg.get("max_depth", 5)
    exit_events: list[str] = journey_cfg.get("exit_events", ["purchase", "session_end"])

    async def _run(s: dict) -> tuple[dict, list[str]]:
        week_start: str = s.get("week_start", "")
        week_end: str = s.get("week_end", "")
        col = get_collection("raw_logs")

        # Collect session paths via aggregation.
        # Sort by event_datetime (ISO string, indexed), group into session paths.
        # $slice truncates to max_depth to limit Python-side payload.
        pipeline = [
            {"$match": {"event_date": {"$gte": week_start, "$lte": week_end}}},
            PREPROCESS_STAGE,
            {"$sort": {
                "user_pseudo_id": 1,
                "ga_session_id": 1,
                "event_datetime": 1,
            }},
            {"$group": {
                "_id": {"user": "$user_pseudo_id", "session": "$ga_session_id"},
                "path": {"$push": "$event_name"},
            }},
            {"$project": {
                "_id": 0,
                "path": {"$slice": ["$path", max_depth]},
            }},
        ]
        session_docs = await col.aggregate(pipeline).to_list(length=None)

        sessions = [{"path": d["path"]} for d in session_docs if d.get("path")]

        converted_paths, churned_paths = _build_path_stats(sessions, exit_events, top_n)
        transition_matrix = _build_transition_matrix(sessions)

        total_sessions = len(sessions)
        converted_sessions = sum(1 for s in sessions if _is_converted(s["path"], exit_events))
        churned_sessions = total_sessions - converted_sessions

        metrics = {
            "converted_paths": converted_paths,
            "churned_paths": churned_paths,
            "transition_matrix": transition_matrix,
            "summary": {
                "total_sessions": total_sessions,
                "converted_sessions": converted_sessions,
                "churned_sessions": churned_sessions,
                "most_common_converted_path": converted_paths[0]["path"] if converted_paths else [],
                "pre_churn_pattern": _pre_churn_pattern(churned_paths),
            },
        }
        return metrics, _validate(metrics)

    journey_metrics, validation_errors = await validate_or_retry(
        run_fn=_run,
        state=state,
        agent_name="journey_agent",
        state_key="journey_metrics",
    )

    summary = journey_metrics.get("summary", {})
    logger.info(
        "journey_agent: total_sessions=%d  converted=%d  churned=%d",
        summary.get("total_sessions", 0),
        summary.get("converted_sessions", 0),
        summary.get("churned_sessions", 0),
    )

    try:
        JourneyMetrics(**journey_metrics)
    except ValidationError as exc:
        logger.warning("journey_agent: schema validation failed — %s", exc)

    return {"journey_metrics": journey_metrics, **error_patch("journey_agent", validation_errors)}

"""Journey & Flow Analysis Agent — session event sequences, top paths, transition matrix.

Input  (PipelineState keys consumed):
    week_start     : str        — "YYYYMMDD"
    week_end       : str        — "YYYYMMDD"
    field_mapping  : dict       — from schema_mapping_agent
    raw_logs       : list[dict] — weekly raw log records
    domain_context : dict       — DomainContext.model_dump()

Output (PipelineState keys produced):
    journey_metrics : dict
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.agents._ga4_utils import get_session_id, in_range

logger = logging.getLogger(__name__)


def _is_converted(path: list[str], exit_events: list[str]) -> bool:
    return any(e in path for e in exit_events if e != "session_end")


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------

def _build_sessions(
    raw_logs: list[dict],
    week_start: str,
    week_end: str,
    max_depth: int,
    entry_events: list[str],
    exit_events: list[str],
) -> list[dict]:
    """Group events into sessions and build truncated event sequences."""
    # {session_key: [(timestamp, event_name), ...]}
    session_events: dict[str, list[tuple[int, str]]] = defaultdict(list)

    for doc in raw_logs:
        event_date = doc.get("event_date", "")
        if not in_range(event_date, week_start, week_end):
            continue
        uid = doc.get("user_pseudo_id", "")
        sid = get_session_id(doc)
        if not uid or not sid:
            continue
        key = f"{uid}_{sid}"
        ts = doc.get("event_timestamp", 0) or 0
        event_name = doc.get("event_name", "")
        session_events[key].append((int(ts), event_name))

    sessions = []
    for key, events in session_events.items():
        sorted_events = [e for _, e in sorted(events, key=lambda x: x[0])]
        # Truncate at max_depth
        path = sorted_events[:max_depth]
        sessions.append({"key": key, "path": path})

    return sessions


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
    """Compute P(B|A) for top_n_nodes most frequent events."""
    pair_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    event_counts: dict[str, int] = defaultdict(int)

    for s in sessions:
        path = s["path"]
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            pair_counts[a][b] += 1
            event_counts[a] += 1

    # Limit to top_n_nodes by frequency
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
# Agent entry point
# ---------------------------------------------------------------------------

async def journey_agent(state: dict) -> dict:
    """LangGraph node: session journey paths, transition matrix, pre-churn pattern."""
    week_start: str = state.get("week_start", "")
    week_end: str = state.get("week_end", "")
    raw_logs: list[dict] = state.get("raw_logs", [])
    domain_context: dict = state.get("domain_context", {})

    journey_cfg: dict = domain_context.get("journey_config", {})
    top_n: int = journey_cfg.get("top_n", 10)
    max_depth: int = journey_cfg.get("max_depth", 5)
    entry_events: list[str] = journey_cfg.get("entry_events", ["session_start"])
    exit_events: list[str] = journey_cfg.get("exit_events", ["purchase", "session_end"])

    sessions = _build_sessions(raw_logs, week_start, week_end, max_depth, entry_events, exit_events)
    converted_paths, churned_paths = _build_path_stats(sessions, exit_events, top_n)
    transition_matrix = _build_transition_matrix(sessions)

    total_sessions = len(sessions)
    converted_sessions = sum(1 for s in sessions if _is_converted(s["path"], exit_events))
    churned_sessions = total_sessions - converted_sessions

    most_common_converted = converted_paths[0]["path"] if converted_paths else []

    journey_metrics = {
        "converted_paths": converted_paths,
        "churned_paths": churned_paths,
        "transition_matrix": transition_matrix,
        "summary": {
            "total_sessions": total_sessions,
            "converted_sessions": converted_sessions,
            "churned_sessions": churned_sessions,
            "most_common_converted_path": most_common_converted,
            "pre_churn_pattern": _pre_churn_pattern(churned_paths),
        },
    }

    logger.info(
        "journey_agent: total_sessions=%d  converted=%d  churned=%d",
        total_sessions,
        converted_sessions,
        churned_sessions,
    )
    return {"journey_metrics": journey_metrics}

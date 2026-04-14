"""Agent smoke test — DB 없이 dummy raw_logs로 전 agent 실행 확인.

실행: python test_agents.py
"""

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ 기준으로 상위 폴더의 .env 로드 (K-PatternHunters/.env)
load_dotenv(Path(__file__).parent.parent / ".env")

# OPENAI_API_KEY 없으면 LLM 호출 agent(anomaly, prediction, schema_mapping)는 skip
SKIP_LLM = not os.environ.get("OPENAI_API_KEY")

# ──────────────────────────────────────────────────────────────────────────────
# Dummy GA4 raw_logs (5주치 — anomaly/prediction baseline용)
# ──────────────────────────────────────────────────────────────────────────────

def _make_doc(
    event_date: str,
    event_name: str,
    uid: str,
    session_id: int,
    revenue: float = 0.0,
    txn_id: str | None = None,
    device: str = "mobile",
    source: str = "google",
    item_category: str = "Apparel",
) -> dict:
    doc: dict = {
        "event_date": event_date,
        "event_name": event_name,
        "event_timestamp": 1609459200000000 + int(event_date) * 1000,
        "user_pseudo_id": uid,
        "event_params": [
            {"key": "ga_session_id", "value": {"int_value": session_id}},
            {"key": "source", "value": {"string_value": source}},
        ],
        "device": {"category": device},
        "traffic_source": {"source": source, "medium": "cpc"},
        "geo": {"country": "KR", "city": "Seoul"},
    }
    if revenue > 0 and txn_id:
        doc["ecommerce"] = {"purchase_revenue": revenue, "transaction_id": txn_id}
        doc["items"] = [{"item_id": "i1", "item_name": "T-shirt", "item_category": item_category, "price": revenue, "quantity": 1}]
    return doc


def build_raw_logs() -> list[dict]:
    logs = []
    # 5주치 데이터: 20201207~20210110
    weeks = [
        ("20201207", "20201213"),
        ("20201214", "20201220"),
        ("20201221", "20201227"),
        ("20201228", "20210103"),
        ("20210104", "20210110"),  # ← 분석 대상 주
    ]
    base_revenue = [100000, 110000, 115000, 120000, 130000]  # 주별 total revenue 증가 추세

    for week_idx, (w_start, w_end) in enumerate(weeks):
        rev = base_revenue[week_idx]
        # 7일치 이벤트 생성
        start_int = int(w_start)
        for day_offset in range(7):
            date = str(start_int + day_offset)
            daily_rev = rev // 7
            # 세션 10개/일
            for i in range(10):
                uid = f"u{week_idx * 70 + day_offset * 10 + i:04d}"
                sid = week_idx * 10000 + day_offset * 100 + i
                device = "mobile" if i % 2 == 0 else "desktop"
                source = "google" if i % 3 != 0 else "direct"
                # funnel events
                logs.append(_make_doc(date, "session_start", uid, sid, device=device, source=source))
                logs.append(_make_doc(date, "view_item", uid, sid, device=device, source=source))
                if i < 6:  # 60% add_to_cart
                    logs.append(_make_doc(date, "add_to_cart", uid, sid, device=device, source=source))
                if i < 4:  # 40% begin_checkout
                    logs.append(_make_doc(date, "begin_checkout", uid, sid, device=device, source=source))
                if i < 2:  # 20% purchase
                    logs.append(_make_doc(
                        date, "purchase", uid, sid,
                        revenue=daily_rev / 2,
                        txn_id=f"txn_{week_idx}_{day_offset}_{i}",
                        device=device,
                        source=source,
                    ))
    return logs


# ──────────────────────────────────────────────────────────────────────────────
# Dummy domain_context (context_agent output 모사)
# ──────────────────────────────────────────────────────────────────────────────

DOMAIN_CONTEXT = {
    "domain": "ecommerce",
    "domain_summary": "GA4 e-commerce sample",
    "analysis_priorities": ["funnel", "performance", "cohort", "journey", "anomaly", "prediction"],
    "recommended_sub_agents": ["funnel", "cohort", "journey", "performance", "anomaly", "prediction"],
    "key_metrics": {"conversion_rate": "purchase / session", "arpu": "revenue / user"},
    "interpretation_guidelines": {},
    "industry_benchmarks": {},
    "funnel_config": {
        "steps": ["session_start", "view_item", "add_to_cart", "begin_checkout", "purchase"]
    },
    "cohort_config": {
        "cohort_basis": "first_purchase_week",
        "user_key": "user_pseudo_id",
        "metrics": ["retention_rate", "avg_revenue"],
    },
    "journey_config": {
        "top_n": 5,
        "max_depth": 5,
        "entry_events": ["session_start"],
        "exit_events": ["purchase", "session_end"],
    },
    "performance_config": {
        "kpis": ["total_revenue", "transaction_count", "arpu", "session_count", "conversion_rate", "bounce_rate"],
        "breakdowns": ["traffic_source", "device_category"],
    },
    "anomaly_config": {
        "target_metrics": ["daily_revenue", "daily_session_count", "daily_conversion_rate"],
        "method": "z_score",
        "threshold": 2.0,
    },
    "prediction_config": {
        "targets": ["next_week_revenue", "next_week_transaction_count"],
        "method": "linear_trend",
        "lookback_weeks": 4,
    },
    "log_schema_hints": {},
    "rag_references": [],
    "search_references": [],
}

STATE = {
    "week_start": "20210104",
    "week_end": "20210110",
    "domain_description": "GA4 e-commerce sample dataset",
    "domain_context": DOMAIN_CONTEXT,
    "raw_logs": build_raw_logs(),
    "field_mapping": {},  # schema_mapping_agent가 채움
}

# ──────────────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────────────

def _print_result(name: str, result: dict) -> None:
    key = list(result.keys())[0]
    data = result[key]
    print(f"\n{'='*60}")
    print(f"  {name}  →  state['{key}']")
    print(f"{'='*60}")
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str)[:1500])
    if len(json.dumps(data, default=str)) > 1500:
        print("  ... (truncated)")


async def main() -> None:
    from app.agents.supervisor import supervisor
    from app.agents.schema_mapping_agent import schema_mapping_agent
    from app.agents.funnel_agent import funnel_agent
    from app.agents.cohort_agent import cohort_agent
    from app.agents.journey_agent import journey_agent
    from app.agents.performance_agent import performance_agent
    from app.agents.anomaly_agent import anomaly_agent
    from app.agents.prediction_agent import prediction_agent

    state = dict(STATE)

    print(f"\n{'#'*60}")
    print(f"  raw_logs: {len(state['raw_logs'])} docs  |  SKIP_LLM={SKIP_LLM}")
    print(f"{'#'*60}")

    # 1. supervisor
    result = await supervisor(state)
    state.update(result)
    _print_result("supervisor", result)

    # 2. schema_mapping
    if SKIP_LLM:
        print("\n[schema_mapping_agent] SKIP_LLM=True → standard mapping only")
        from app.agents.schema_mapping_agent import _STANDARD_GA4_MAPPING
        state["field_mapping"] = dict(_STANDARD_GA4_MAPPING)
        print(f"  field_mapping keys: {len(state['field_mapping'])}")
    else:
        result = await schema_mapping_agent(state)
        state.update(result)
        _print_result("schema_mapping_agent", result)

    # 3. 분석 agents (순차 실행 — 테스트용, 실제 pipeline은 병렬)
    agents = [
        ("funnel_agent", funnel_agent),
        ("cohort_agent", cohort_agent),
        ("journey_agent", journey_agent),
        ("performance_agent", performance_agent),
    ]
    for name, fn in agents:
        result = await fn(state)
        state.update(result)
        _print_result(name, result)

    # 4. LLM agents
    if SKIP_LLM:
        print("\n[anomaly_agent / prediction_agent] OPENAI_API_KEY not set — skipping LLM agents")
        print("  Set OPENAI_API_KEY env var to test these.")
    else:
        for name, fn in [("anomaly_agent", anomaly_agent), ("prediction_agent", prediction_agent)]:
            result = await fn(state)
            state.update(result)
            _print_result(name, result)

    print(f"\n{'#'*60}")
    print("  All agents completed successfully")
    print(f"{'#'*60}\n")


if __name__ == "__main__":
    asyncio.run(main())

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
# Dummy InsightReport (insight_agent 없이 ppt_agent 단독 테스트용)
# ──────────────────────────────────────────────────────────────────────────────

def _slide(slide_type: str, title: str, headline: str, chart_type: str, data_key: str) -> dict:
    return {
        "slide_type": slide_type,
        "title": title,
        "headline": headline,
        "bullets": [
            f"{title} 관련 주요 발견 1: 전환율이 전주 대비 5% 상승했습니다.",
            f"{title} 관련 주요 발견 2: 모바일 트래픽 비중이 60%를 차지했습니다.",
            f"{title} 관련 주요 발견 3: 직접 유입 채널의 전환율이 가장 높았습니다.",
        ],
        "metrics": {"핵심지표A": "1,234", "핵심지표B": "5.6%"},
        "chart_type": chart_type,
        "chart_data_key": data_key,
        "speaker_notes": f"{title} 슬라이드 발표자 노트입니다.",
    }


def _make_dummy_insight_report() -> dict:
    return {
        "domain": "ecommerce",
        "analysis_period": "2021-W01 (Jan 4–10)",
        "overall_sentiment": "positive",
        "executive_summary": (
            "이번 주 전체 매출은 전주 대비 8.3% 증가하며 긍정적인 성장세를 보였습니다. "
            "전환율은 20%로 업계 평균인 15%를 상회하고 있으며, "
            "모바일 채널이 전체 세션의 60%를 차지하는 등 모바일 중심의 트래픽 구조가 확인됩니다. "
            "다음 주 매출은 현재 추세 기준 약 14만원 수준으로 예측됩니다."
        ),
        "top_findings": [
            "전체 매출 130,000원, 전주 대비 +8.3% 성장",
            "구매 전환율 20%로 업계 평균(15%) 초과 달성",
            "모바일 트래픽 60%, 데스크톱 대비 전환율 5%p 높음",
            "add_to_cart → begin_checkout 구간 이탈률이 가장 높음 (40%)",
            "코호트 Week1 재구매율 평균 15%로 안정적 수준 유지",
        ],
        "recommendations": [
            "add_to_cart → begin_checkout 이탈 구간 UX 개선 — 해당 구간 이탈률 40%로 가장 높음",
            "모바일 최적화 집중 투자 — 모바일이 전체 세션 60% 차지하며 전환율도 높음",
            "google 채널 예산 확대 — 전환율 및 매출 기여도 1위",
            "Week1 재구매 촉진 캠페인 실행 — 코호트 Week1 이탈이 가장 큰 이탈 시점",
            "다음 주 매출 목표 14만원으로 설정 — 선형 추세 기반 예측값",
        ],
        "performance_slide": _slide("performance", "주요 지표 현황", "매출 8.3% 성장, 전환율 20% 달성", "kpi_cards", "performance_metrics"),
        "funnel_slide":      _slide("funnel", "사용자 흐름 분석", "add_to_cart 이탈이 최대 병목", "funnel_chart", "funnel_metrics"),
        "cohort_slide":      _slide("cohort", "고객 세그먼트 분석", "Week1 재구매율 15% 안정적 유지", "heatmap", "cohort_metrics"),
        "journey_slide":     _slide("journey", "사용자 여정 분석", "전환 경로 Top 3 집중 현상 확인", "sankey", "journey_metrics"),
        "anomaly_slide":     _slide("anomaly", "이상 감지 결과", "이번 주 이상 감지 없음", "table", "anomaly_metrics"),
        "prediction_slide":  _slide("prediction", "예측 및 시사점", "다음 주 매출 14만원 예측 (상승 추세)", "line_chart", "prediction_metrics"),
        "cross_analysis_findings": [
            "퍼널 이탈 구간(add_to_cart)과 모바일 이탈률 상관관계 확인 필요",
            "google 채널 유입 증가와 이번 주 매출 성장 간 직접적 연관성 있음",
        ],
        "slide_order": [
            "executive_summary", "performance", "anomaly",
            "funnel", "cohort", "domain", "prediction", "recommendations",
        ],
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
    from app.agents.schema_mapping_agent import schema_mapping_agent
    from app.agents.funnel_agent import funnel_agent
    from app.agents.cohort_agent import cohort_agent
    from app.agents.journey_agent import journey_agent
    from app.agents.performance_agent import performance_agent
    from app.agents.anomaly_agent import anomaly_agent
    from app.agents.prediction_agent import prediction_agent

    state = dict(STATE)

    print(f"\n{'#'*60}")
    print(f"  raw_logs: {len(state['raw_logs'])} docs")
    print(f"{'#'*60}")

    # 1. schema_mapping
    result = await schema_mapping_agent(state)
    state.update(result)
    _print_result("schema_mapping_agent", result)

    # 2. 분석 agents (순차 실행 — 테스트용, 실제 pipeline은 병렬)
    for name, fn in [
        ("funnel_agent",      funnel_agent),
        ("cohort_agent",      cohort_agent),
        ("journey_agent",     journey_agent),
        ("performance_agent", performance_agent),
        ("anomaly_agent",     anomaly_agent),
        ("prediction_agent",  prediction_agent),
    ]:
        result = await fn(state)
        state.update(result)
        _print_result(name, result)

    # 3. insight_agent — 실제 LLM 호출로 InsightReport 생성
    print("\n[insight_agent] LLM 실제 호출로 InsightReport 생성 중...")
    from app.agents.insight_agent import insight_agent
    result = await insight_agent(state)
    state.update(result)
    _print_result("insight_agent", result)

    # 4. ppt_agent — insight_agent 실제 출력 사용
    print("\n[ppt_agent] insight_agent 실제 출력으로 PPT 생성")
    from app.agents.ppt_agent import ppt_agent
    ppt_result = await ppt_agent(state)
    state.update(ppt_result)
    ppt_path = ppt_result.get("ppt_url", "")
    exists = os.path.exists(ppt_path)
    print(f"  ppt_url  : {ppt_path}")
    print(f"  파일 존재 : {exists}")
    if exists:
        size_kb = os.path.getsize(ppt_path) // 1024
        print(f"  파일 크기 : {size_kb} KB")

    print(f"\n{'#'*60}")
    print("  All agents completed successfully")
    print(f"{'#'*60}\n")


if __name__ == "__main__":
    asyncio.run(main())

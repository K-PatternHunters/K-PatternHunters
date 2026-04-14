"""PPT Report Agent — generates an 8-slide PowerPoint report from insight_report + raw metrics.

Input  (PipelineState keys consumed):
    insight_report      : dict   — InsightReport.model_dump() from insight_agent
    performance_metrics : dict   — from performance_agent
    funnel_metrics      : dict   — from funnel_agent
    cohort_metrics      : dict   — from cohort_agent
    journey_metrics     : dict   — from journey_agent
    anomaly_metrics     : dict   — from anomaly_agent
    prediction_metrics  : dict   — from prediction_agent
    domain_context      : dict   — DomainContext.model_dump() from context_agent
    week_start          : str    — "YYYYMMDD"
    week_end            : str    — "YYYYMMDD"

Output (PipelineState key produced):
    ppt_url : str   — local file path (or object-storage URL) of the generated .pptx

Slide structure (fixed 8 slides):
    Slide 1  Executive Summary      — KPI 카드 3개 + 한 줄 요약
    Slide 2  주요 지표 현황           — 일별 지표 테이블 + WoW 증감
    Slide 3  이상 감지 결과           — 이상값 강조 테이블
    Slide 4  사용자 흐름 분석         — 퍼널 단계별 이탈 + 주요 경로
    Slide 5  고객 세그먼트 분석        — 디바이스/소스별 비교
    Slide 6  [도메인 가변 슬라이드]    — e-commerce: 카테고리별 구매 분석
    Slide 7  예측 및 시사점           — 다음 주 예측값 + LLM 코멘트
    Slide 8  권장 액션               — LLM recommendations + 우선순위
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Layout / theme constants
# ──────────────────────────────────────────────────────────────────────────────

_SLIDE_W = Inches(13.33)
_SLIDE_H = Inches(7.5)

_COLOR = {
    "bg_dark":    RGBColor(0x1A, 0x1A, 0x2E),   # 배경 (진남색)
    "bg_card":    RGBColor(0x16, 0x21, 0x3E),   # 카드 배경
    "accent":     RGBColor(0x0F, 0x3A, 0x6E),   # 강조 파란색
    "positive":   RGBColor(0x27, 0xAE, 0x60),   # 증가 초록
    "negative":   RGBColor(0xE7, 0x4C, 0x3C),   # 감소/이상 빨강
    "neutral":    RGBColor(0xF3, 0x9C, 0x12),   # 중립 주황
    "white":      RGBColor(0xFF, 0xFF, 0xFF),
    "light_gray": RGBColor(0xCC, 0xCC, 0xCC),
    "header_bg":  RGBColor(0x0F, 0x3A, 0x6E),
}

_OUTPUT_DIR = os.environ.get("PPT_OUTPUT_DIR", "/tmp/ppt_reports")


# ──────────────────────────────────────────────────────────────────────────────
# Low-level drawing helpers
# ──────────────────────────────────────────────────────────────────────────────

def _add_rect(slide, left, top, width, height, fill_color: RGBColor, alpha: int | None = None):
    from pptx.util import Emu
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        left, top, width, height,
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    return shape


def _add_textbox(
    slide,
    text: str,
    left, top, width, height,
    font_size: int = 14,
    bold: bool = False,
    color: RGBColor = _COLOR["white"],
    align: PP_ALIGN = PP_ALIGN.LEFT,
    wrap: bool = True,
) -> None:
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color


def _slide_background(slide, color: RGBColor = _COLOR["bg_dark"]) -> None:
    """Fill slide background with a solid color."""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_slide_header(slide, title: str, subtitle: str = "") -> None:
    """Add a colored header bar with title + optional subtitle."""
    _add_rect(slide, Inches(0), Inches(0), _SLIDE_W, Inches(1.2), _COLOR["header_bg"])
    _add_textbox(
        slide, title,
        Inches(0.3), Inches(0.1), Inches(10), Inches(0.7),
        font_size=28, bold=True, color=_COLOR["white"],
    )
    if subtitle:
        _add_textbox(
            slide, subtitle,
            Inches(0.3), Inches(0.75), Inches(10), Inches(0.4),
            font_size=14, color=_COLOR["light_gray"],
        )


def _add_kpi_card(slide, label: str, value: str, delta: str, left, top, width=Inches(3.5), height=Inches(1.8)) -> None:
    """Draw a KPI card: label / big value / delta arrow."""
    _add_rect(slide, left, top, width, height, _COLOR["bg_card"])
    _add_textbox(slide, label, left + Inches(0.15), top + Inches(0.1), width - Inches(0.3), Inches(0.4),
                 font_size=12, color=_COLOR["light_gray"])
    _add_textbox(slide, value, left + Inches(0.15), top + Inches(0.45), width - Inches(0.3), Inches(0.7),
                 font_size=26, bold=True, color=_COLOR["white"])
    delta_color = _COLOR["positive"] if delta.startswith("+") else (_COLOR["negative"] if delta.startswith("-") else _COLOR["light_gray"])
    _add_textbox(slide, delta, left + Inches(0.15), top + Inches(1.2), width - Inches(0.3), Inches(0.4),
                 font_size=13, color=delta_color)


def _add_table(
    slide,
    headers: list[str],
    rows: list[list[str]],
    left, top, width, height,
    highlight_rows: set[int] | None = None,
) -> None:
    """Add a basic table; highlight_rows indices are colored red."""
    if not rows:
        _add_textbox(slide, "(데이터 없음)", left, top, width, height,
                     font_size=12, color=_COLOR["light_gray"])
        return

    cols = len(headers)
    row_count = len(rows) + 1  # +1 for header
    table = slide.shapes.add_table(row_count, cols, left, top, width, height).table

    col_width = width // cols
    for i in range(cols):
        table.columns[i].width = col_width

    # Header row
    for c, h in enumerate(headers):
        cell = table.cell(0, c)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = _COLOR["header_bg"]
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.runs[0] if p.runs else p.add_run()
        run.font.bold = True
        run.font.color.rgb = _COLOR["white"]
        run.font.size = Pt(11)

    # Data rows
    for r, row in enumerate(rows):
        is_highlight = highlight_rows and r in highlight_rows
        bg = _COLOR["negative"] if is_highlight else (
            RGBColor(0x1E, 0x2D, 0x4A) if r % 2 == 0 else _COLOR["bg_card"]
        )
        for c, val in enumerate(row):
            cell = table.cell(r + 1, c)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = bg
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            run = p.runs[0] if p.runs else p.add_run()
            run.font.color.rgb = _COLOR["white"]
            run.font.size = Pt(10)


def _fmt_num(v: Any, prefix: str = "", suffix: str = "", decimals: int = 0) -> str:
    try:
        f = float(v)
        if decimals:
            return f"{prefix}{f:,.{decimals}f}{suffix}"
        return f"{prefix}{int(f):,}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_pct(v: Any, decimals: int = 1) -> str:
    try:
        return f"{float(v) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return str(v)


def _wow_str(v: Any) -> str:
    if v is None:
        return "—"
    try:
        pct = float(v) * 100
        return f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
    except (TypeError, ValueError):
        return str(v)


# ──────────────────────────────────────────────────────────────────────────────
# Per-slide builders
# ──────────────────────────────────────────────────────────────────────────────

def _build_slide1_executive_summary(slide, insight_report: dict, performance_metrics: dict) -> None:
    """Slide 1: Executive Summary — KPI 카드 3개 + 한 줄 요약."""
    _slide_background(slide)
    _add_slide_header(slide, "Executive Summary", "주간 핵심 성과 요약")

    kpis = (performance_metrics or {}).get("kpis", {})
    wow = (performance_metrics or {}).get("wow_change") or {}

    cards = [
        ("총 매출", _fmt_num(kpis.get("total_revenue", 0), prefix="₩", decimals=0),
         _wow_str(wow.get("total_revenue"))),
        ("전환율", _fmt_pct(kpis.get("conversion_rate", 0)),
         _wow_str(wow.get("conversion_rate"))),
        ("세션 수", _fmt_num(kpis.get("session_count", 0)),
         _wow_str(wow.get("session_count"))),
    ]

    card_top = Inches(1.4)
    card_w = Inches(3.8)
    card_h = Inches(1.9)
    for i, (label, value, delta) in enumerate(cards):
        left = Inches(0.4 + i * 4.3)
        _add_kpi_card(slide, label, value, delta, left, card_top, card_w, card_h)

    # Executive summary text
    summary = (insight_report or {}).get("executive_summary", "")
    _add_rect(slide, Inches(0.4), Inches(3.5), Inches(12.5), Inches(2.5), _COLOR["bg_card"])
    _add_textbox(
        slide, "핵심 요약",
        Inches(0.6), Inches(3.6), Inches(12), Inches(0.4),
        font_size=13, bold=True, color=_COLOR["light_gray"],
    )
    _add_textbox(
        slide, summary or "(요약 없음)",
        Inches(0.6), Inches(4.0), Inches(12.2), Inches(1.8),
        font_size=13, color=_COLOR["white"], wrap=True,
    )


def _build_slide2_performance(slide, performance_metrics: dict, insight_report: dict) -> None:
    """Slide 2: 주요 지표 현황 — 일별 테이블 + WoW."""
    _slide_background(slide)
    perf_slide = (insight_report or {}).get("performance_slide") or {}
    headline = perf_slide.get("headline", "")
    _add_slide_header(slide, "주요 지표 현황", headline)

    kpis = (performance_metrics or {}).get("kpis", {})
    wow = (performance_metrics or {}).get("wow_change") or {}

    # KPI summary row
    kpi_rows = [
        ["지표", "이번 주", "전주 대비"],
        ["총 매출", _fmt_num(kpis.get("total_revenue", 0), prefix="₩"), _wow_str(wow.get("total_revenue"))],
        ["거래 건수", _fmt_num(kpis.get("transaction_count", 0)), _wow_str(wow.get("transaction_count"))],
        ["세션 수", _fmt_num(kpis.get("session_count", 0)), _wow_str(wow.get("session_count"))],
        ["전환율", _fmt_pct(kpis.get("conversion_rate", 0)), _wow_str(wow.get("conversion_rate"))],
        ["이탈률", _fmt_pct(kpis.get("bounce_rate", 0)), "—"],
        ["ARPU", _fmt_num(kpis.get("arpu", 0), prefix="₩", decimals=0), "—"],
    ]

    _add_table(
        slide, kpi_rows[0], kpi_rows[1:],
        Inches(0.4), Inches(1.4), Inches(5.5), Inches(4.0),
    )

    # Daily breakdown (last 7 days)
    daily = (performance_metrics or {}).get("daily_breakdown", [])[-7:]
    if daily:
        _add_textbox(slide, "일별 현황", Inches(6.3), Inches(1.35), Inches(6.5), Inches(0.4),
                     font_size=13, bold=True, color=_COLOR["light_gray"])
        daily_rows = [
            [d.get("date", ""), _fmt_num(d.get("revenue", 0), prefix="₩"),
             _fmt_num(d.get("session_count", 0)), _fmt_num(d.get("transaction_count", 0))]
            for d in daily
        ]
        _add_table(
            slide, ["날짜", "매출", "세션", "거래"],
            daily_rows,
            Inches(6.3), Inches(1.75), Inches(6.5), Inches(3.8),
        )


def _build_slide3_anomaly(slide, anomaly_metrics: dict, insight_report: dict) -> None:
    """Slide 3: 이상 감지 결과 — 이상값 강조 테이블."""
    _slide_background(slide)
    anomaly_slide = (insight_report or {}).get("anomaly_slide") or {}
    headline = anomaly_slide.get("headline", "")
    _add_slide_header(slide, "이상 감지 결과", headline)

    anomalies = (anomaly_metrics or {}).get("anomalies", [])
    summary = (anomaly_metrics or {}).get("summary", {})

    # Summary cards
    total = summary.get("total_anomalies", 0)
    affected = ", ".join(summary.get("affected_metrics", [])) or "없음"
    worst_date = summary.get("most_abnormal_date") or "—"

    _add_kpi_card(slide, "감지된 이상 수", str(total), "", Inches(0.4), Inches(1.4), Inches(2.5), Inches(1.5))
    _add_kpi_card(slide, "영향 지표", affected[:30], "", Inches(3.2), Inches(1.4), Inches(4.5), Inches(1.5))
    _add_kpi_card(slide, "가장 이상한 날짜", worst_date, "", Inches(8.0), Inches(1.4), Inches(2.5), Inches(1.5))

    if anomalies:
        rows = [
            [
                a.get("metric", ""),
                a.get("date", ""),
                _fmt_num(a.get("observed_value", 0), decimals=2),
                _fmt_num(a.get("expected_mean", 0), decimals=2),
                f"{a.get('z_score', 0):+.2f}",
                a.get("direction", ""),
            ]
            for a in anomalies[:12]
        ]
        highlight = {i for i, a in enumerate(anomalies[:12]) if abs(a.get("z_score", 0)) >= 3}
        _add_table(
            slide, ["지표", "날짜", "관측값", "기댓값", "Z-score", "방향"],
            rows,
            Inches(0.4), Inches(3.1), Inches(12.5), Inches(3.5),
            highlight_rows=highlight,
        )

        # LLM interpretation for top anomaly
        top = max(anomalies, key=lambda a: abs(a.get("z_score", 0)), default=None)
        if top and top.get("llm_interpretation"):
            _add_textbox(
                slide, f"해석: {top['llm_interpretation']}",
                Inches(0.4), Inches(6.7), Inches(12.5), Inches(0.6),
                font_size=11, color=_COLOR["light_gray"], wrap=True,
            )
    else:
        _add_textbox(
            slide, "이번 주 이상 감지된 지표 없음",
            Inches(0.4), Inches(3.1), Inches(12.5), Inches(1.0),
            font_size=18, color=_COLOR["positive"], align=PP_ALIGN.CENTER,
        )


def _build_slide4_funnel_journey(slide, funnel_metrics: dict, journey_metrics: dict, insight_report: dict) -> None:
    """Slide 4: 사용자 흐름 분석 — 퍼널 + 주요 경로."""
    _slide_background(slide)
    funnel_slide = (insight_report or {}).get("funnel_slide") or {}
    headline = funnel_slide.get("headline", "")
    _add_slide_header(slide, "사용자 흐름 분석", headline)

    # Funnel table
    steps = (funnel_metrics or {}).get("steps", [])
    if steps:
        _add_textbox(slide, "퍼널 단계별 전환", Inches(0.4), Inches(1.35), Inches(6.0), Inches(0.4),
                     font_size=13, bold=True, color=_COLOR["light_gray"])
        funnel_rows = [
            [
                s.get("event_name", ""),
                _fmt_num(s.get("user_count", 0)),
                _fmt_pct(s.get("conversion_rate", 0)),
                f"{s.get('drop_off_rate', 0):.1f}%",
            ]
            for s in steps
        ]
        _add_table(
            slide, ["단계", "유저 수", "누적 전환율", "이탈률"],
            funnel_rows,
            Inches(0.4), Inches(1.75), Inches(6.0), Inches(4.2),
        )

    # Top converted paths
    converted = (journey_metrics or {}).get("converted_paths", [])[:5]
    if converted:
        _add_textbox(slide, "주요 전환 경로 Top 5", Inches(6.8), Inches(1.35), Inches(6.0), Inches(0.4),
                     font_size=13, bold=True, color=_COLOR["light_gray"])
        path_rows = [
            [" → ".join(p.get("path", [])), _fmt_num(p.get("session_count", 0)), _fmt_pct(p.get("ratio", 0))]
            for p in converted
        ]
        _add_table(
            slide, ["경로", "세션 수", "비율"],
            path_rows,
            Inches(6.8), Inches(1.75), Inches(6.1), Inches(2.5),
        )

    # Pre-churn pattern
    journey_summary = (journey_metrics or {}).get("summary", {})
    pre_churn = journey_summary.get("pre_churn_pattern", "")
    if pre_churn:
        _add_rect(slide, Inches(6.8), Inches(4.4), Inches(6.1), Inches(0.9), _COLOR["bg_card"])
        _add_textbox(slide, f"주요 이탈 패턴:  {pre_churn}",
                     Inches(7.0), Inches(4.5), Inches(5.8), Inches(0.7),
                     font_size=13, color=_COLOR["negative"])


def _build_slide5_segment(slide, performance_metrics: dict, cohort_metrics: dict, insight_report: dict) -> None:
    """Slide 5: 고객 세그먼트 분석 — 디바이스/소스 비교 + 코호트 요약."""
    _slide_background(slide)
    cohort_slide = (insight_report or {}).get("cohort_slide") or {}
    headline = cohort_slide.get("headline", "")
    _add_slide_header(slide, "고객 세그먼트 분석", headline)

    # By device
    by_device = (performance_metrics or {}).get("by_device_category", [])[:6]
    if by_device:
        _add_textbox(slide, "디바이스별", Inches(0.4), Inches(1.35), Inches(4.0), Inches(0.4),
                     font_size=13, bold=True, color=_COLOR["light_gray"])
        rows = [
            [d.get("device", ""), _fmt_num(d.get("session_count", 0)),
             _fmt_pct(d.get("conversion_rate", 0)), _fmt_num(d.get("revenue", 0), prefix="₩")]
            for d in by_device
        ]
        _add_table(slide, ["디바이스", "세션", "전환율", "매출"],
                   rows, Inches(0.4), Inches(1.75), Inches(5.8), Inches(2.8))

    # By traffic source
    by_source = (performance_metrics or {}).get("by_traffic_source", [])[:6]
    if by_source:
        _add_textbox(slide, "트래픽 소스별", Inches(6.7), Inches(1.35), Inches(6.0), Inches(0.4),
                     font_size=13, bold=True, color=_COLOR["light_gray"])
        rows = [
            [s.get("source", "")[:20], _fmt_num(s.get("session_count", 0)),
             _fmt_pct(s.get("conversion_rate", 0)), _fmt_num(s.get("revenue", 0), prefix="₩")]
            for s in by_source
        ]
        _add_table(slide, ["소스", "세션", "전환율", "매출"],
                   rows, Inches(6.7), Inches(1.75), Inches(6.2), Inches(2.8))

    # Cohort summary
    cohort_summary = (cohort_metrics or {}).get("summary", {})
    if cohort_summary:
        _add_rect(slide, Inches(0.4), Inches(4.8), Inches(12.5), Inches(1.8), _COLOR["bg_card"])
        _add_textbox(slide, "코호트 분석 요약",
                     Inches(0.6), Inches(4.9), Inches(12.0), Inches(0.35),
                     font_size=12, bold=True, color=_COLOR["light_gray"])
        cohort_text = (
            f"Week 1 평균 재구매율: {_fmt_pct(cohort_summary.get('avg_week1_retention', 0))}  |  "
            f"최고 리텐션 코호트: {cohort_summary.get('best_retention_cohort') or '—'}  |  "
            f"신규 구매자 트렌드: {cohort_summary.get('new_buyer_trend', '—')}"
        )
        _add_textbox(slide, cohort_text,
                     Inches(0.6), Inches(5.25), Inches(12.0), Inches(1.2),
                     font_size=13, color=_COLOR["white"], wrap=True)


def _build_slide6_domain(slide, domain: str, performance_metrics: dict, insight_report: dict) -> None:
    """Slide 6: 도메인 가변 슬라이드.

    e-commerce (기본): 카테고리별 구매 분석.
    다른 도메인으로 교체 시 이 함수만 수정 또는 도메인별 함수를 추가.
    """
    _slide_background(slide)

    domain_lower = (domain or "ecommerce").lower().replace("-", "").replace(" ", "")

    if "ecommerce" in domain_lower or "commerce" in domain_lower:
        _add_slide_header(slide, "카테고리별 구매 분석", "e-Commerce 도메인 심화 분석")
        by_category = (performance_metrics or {}).get("by_item_category", [])[:10]
        if by_category:
            rows = [
                [
                    c.get("category", "")[:20],
                    _fmt_num(c.get("view_count", 0)),
                    _fmt_num(c.get("add_to_cart_count", 0)),
                    _fmt_num(c.get("purchase_count", 0)),
                    _fmt_num(c.get("revenue", 0), prefix="₩"),
                    _fmt_pct(c.get("purchase_rate", 0)),
                ]
                for c in by_category
            ]
            _add_table(
                slide, ["카테고리", "조회", "장바구니", "구매", "매출", "구매율"],
                rows,
                Inches(0.4), Inches(1.4), Inches(12.5), Inches(5.0),
            )
        else:
            _add_textbox(slide, "(카테고리 데이터 없음)", Inches(0.4), Inches(3.0), Inches(12.5), Inches(1.0),
                         font_size=16, color=_COLOR["light_gray"], align=PP_ALIGN.CENTER)

    elif "fintech" in domain_lower or "finance" in domain_lower:
        _add_slide_header(slide, "금융 상품 분석", "Fintech 도메인 심화 분석")
        # Placeholder — 실제 구현 시 fintech 전용 지표 추가
        _add_textbox(slide, "Fintech 도메인: 금융 상품별 전환 및 리텐션 분석 (구현 예정)",
                     Inches(0.4), Inches(2.5), Inches(12.5), Inches(2.0),
                     font_size=16, color=_COLOR["light_gray"], align=PP_ALIGN.CENTER)

    elif "media" in domain_lower or "content" in domain_lower:
        _add_slide_header(slide, "콘텐츠 소비 분석", "Media 도메인 심화 분석")
        _add_textbox(slide, "Media 도메인: 콘텐츠 유형별 참여율 및 완독률 분석 (구현 예정)",
                     Inches(0.4), Inches(2.5), Inches(12.5), Inches(2.0),
                     font_size=16, color=_COLOR["light_gray"], align=PP_ALIGN.CENTER)

    else:
        _add_slide_header(slide, f"{domain} 도메인 분석", "도메인 특화 분석")
        _add_textbox(
            slide, f"'{domain}' 도메인의 특화 분석 슬라이드입니다.\n"
                   "도메인 컨텍스트에 맞게 이 슬라이드를 커스터마이징하세요.",
            Inches(0.4), Inches(2.5), Inches(12.5), Inches(2.0),
            font_size=15, color=_COLOR["light_gray"], wrap=True,
        )


def _build_slide7_prediction(slide, prediction_metrics: dict, insight_report: dict) -> None:
    """Slide 7: 예측 및 시사점 — 다음 주 예측값 + LLM 코멘트."""
    _slide_background(slide)
    pred_slide = (insight_report or {}).get("prediction_slide") or {}
    headline = pred_slide.get("headline", "")
    _add_slide_header(slide, "예측 및 시사점", headline)

    predictions = (prediction_metrics or {}).get("predictions", [])
    pred_summary = (prediction_metrics or {}).get("summary", {})
    overall_trend = pred_summary.get("overall_trend", "stable")
    dq_warning = pred_summary.get("data_quality_warning")

    trend_color = {
        "increasing": _COLOR["positive"],
        "decreasing": _COLOR["negative"],
        "stable":     _COLOR["neutral"],
    }.get(overall_trend, _COLOR["neutral"])

    _add_rect(slide, Inches(0.4), Inches(1.35), Inches(4.0), Inches(0.7), _COLOR["bg_card"])
    _add_textbox(slide, f"전반적 추세: {overall_trend}",
                 Inches(0.6), Inches(1.45), Inches(3.8), Inches(0.5),
                 font_size=16, bold=True, color=trend_color)

    if dq_warning:
        _add_textbox(slide, f"⚠ {dq_warning}",
                     Inches(4.8), Inches(1.45), Inches(7.5), Inches(0.5),
                     font_size=12, color=_COLOR["neutral"])

    if predictions:
        rows = []
        for p in predictions:
            ci = p.get("confidence_interval", {})
            skipped = p.get("skipped", False)
            rows.append([
                p.get("target", ""),
                _fmt_num(p.get("predicted_value", 0), decimals=2) if not skipped else "데이터 부족",
                f"{_fmt_num(ci.get('lower', 0), decimals=2)} ~ {_fmt_num(ci.get('upper', 0), decimals=2)}" if not skipped else "—",
                p.get("trend_direction", ""),
                p.get("llm_comment", "") or "—",
            ])

        _add_table(
            slide, ["예측 지표", "예측값", "신뢰구간", "추세", "코멘트"],
            rows,
            Inches(0.4), Inches(2.1), Inches(12.5), Inches(3.5),
        )

    # Bullets from insight_report
    bullets = pred_slide.get("bullets", [])
    if bullets:
        y = Inches(5.75)
        for bullet in bullets[:3]:
            _add_textbox(slide, f"• {bullet}", Inches(0.4), y, Inches(12.5), Inches(0.4),
                         font_size=11, color=_COLOR["light_gray"])
            y += Inches(0.35)


def _build_slide8_recommendations(slide, insight_report: dict) -> None:
    """Slide 8: 권장 액션 — LLM recommendations + 우선순위."""
    _slide_background(slide)
    _add_slide_header(slide, "권장 액션", "컨텍스트 기반 우선순위 권장사항 (RAG 적용)")

    recommendations = (insight_report or {}).get("recommendations", [])
    cross_findings = (insight_report or {}).get("cross_analysis_findings", [])

    priority_colors = [_COLOR["negative"], _COLOR["neutral"], _COLOR["positive"]]
    priority_labels = ["P1", "P2", "P3"]

    if recommendations:
        _add_textbox(slide, "권장 액션",
                     Inches(0.4), Inches(1.35), Inches(9.0), Inches(0.4),
                     font_size=14, bold=True, color=_COLOR["light_gray"])
        y = Inches(1.8)
        for i, rec in enumerate(recommendations[:5]):
            color = priority_colors[min(i, 2)]
            label = priority_labels[min(i, 2)]
            _add_rect(slide, Inches(0.4), y, Inches(0.6), Inches(0.45), color)
            _add_textbox(slide, label, Inches(0.4), y, Inches(0.6), Inches(0.45),
                         font_size=12, bold=True, color=_COLOR["white"], align=PP_ALIGN.CENTER)
            _add_textbox(slide, rec, Inches(1.1), y, Inches(11.5), Inches(0.45),
                         font_size=12, color=_COLOR["white"], wrap=True)
            y += Inches(0.6)

    if cross_findings:
        _add_textbox(slide, "교차 분석 인사이트",
                     Inches(0.4), Inches(5.0), Inches(12.5), Inches(0.4),
                     font_size=13, bold=True, color=_COLOR["light_gray"])
        y = Inches(5.45)
        for finding in cross_findings[:3]:
            _add_textbox(slide, f"▸ {finding}", Inches(0.4), y, Inches(12.5), Inches(0.4),
                         font_size=11, color=_COLOR["light_gray"], wrap=True)
            y += Inches(0.45)


# ──────────────────────────────────────────────────────────────────────────────
# Main builder
# ──────────────────────────────────────────────────────────────────────────────

def _build_presentation(state: dict) -> Presentation:
    insight_report      = state.get("insight_report") or {}
    performance_metrics = state.get("performance_metrics") or {}
    funnel_metrics      = state.get("funnel_metrics") or {}
    cohort_metrics      = state.get("cohort_metrics") or {}
    journey_metrics     = state.get("journey_metrics") or {}
    anomaly_metrics     = state.get("anomaly_metrics") or {}
    prediction_metrics  = state.get("prediction_metrics") or {}
    domain_context      = state.get("domain_context") or {}
    domain              = domain_context.get("domain", "ecommerce")

    prs = Presentation()
    prs.slide_width = _SLIDE_W
    prs.slide_height = _SLIDE_H

    blank_layout = prs.slide_layouts[6]  # completely blank

    builders = [
        lambda s: _build_slide1_executive_summary(s, insight_report, performance_metrics),
        lambda s: _build_slide2_performance(s, performance_metrics, insight_report),
        lambda s: _build_slide3_anomaly(s, anomaly_metrics, insight_report),
        lambda s: _build_slide4_funnel_journey(s, funnel_metrics, journey_metrics, insight_report),
        lambda s: _build_slide5_segment(s, performance_metrics, cohort_metrics, insight_report),
        lambda s: _build_slide6_domain(s, domain, performance_metrics, insight_report),
        lambda s: _build_slide7_prediction(s, prediction_metrics, insight_report),
        lambda s: _build_slide8_recommendations(s, insight_report),
    ]

    for build_fn in builders:
        slide = prs.slides.add_slide(blank_layout)
        build_fn(slide)

    return prs


# ──────────────────────────────────────────────────────────────────────────────
# Agent entry point
# ──────────────────────────────────────────────────────────────────────────────

async def ppt_agent(state: dict) -> dict:
    """LangGraph node: generate an 8-slide PowerPoint report."""
    if not state.get("insight_report"):
        raise ValueError("ppt_agent: 'insight_report' must be present in pipeline state")

    week_start = state.get("week_start", "unknown")
    week_end   = state.get("week_end", "unknown")
    domain     = (state.get("domain_context") or {}).get("domain", "report")

    prs = _build_presentation(state)

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{domain}_{week_start}_{week_end}_{timestamp}.pptx"
    filepath = os.path.join(_OUTPUT_DIR, filename)
    prs.save(filepath)

    logger.info("ppt_agent: saved report → %s", filepath)
    return {"ppt_url": filepath}

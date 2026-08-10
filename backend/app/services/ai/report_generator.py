"""
LiveIQ — Executive PDF Report Generator (Sprint 5E)
Builds a stakeholder-ready PDF from real KPI/portfolio/briefing data
already served by /executive/*. No fabricated figures — any section with
no real data renders an explicit "no data" note instead of a placeholder
number, and there is no city map (no Mapbox integration exists yet); city
coverage is shown as a real data table instead.
"""

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

ACCENT = colors.HexColor("#0a84ff")
TEXT_DARK = colors.HexColor("#1c1c1e")
TEXT_MUTED = colors.HexColor("#6e6e73")
DIVIDER = colors.HexColor("#e5e5ea")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ReportTitle", parent=base["Title"], fontSize=22, textColor=TEXT_DARK, spaceAfter=2),
        "subtitle": ParagraphStyle("ReportSubtitle", parent=base["Normal"], fontSize=10, textColor=TEXT_MUTED, spaceAfter=16),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontSize=14, textColor=TEXT_DARK, spaceBefore=18, spaceAfter=8),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=10, textColor=TEXT_DARK, leading=15),
        "muted": ParagraphStyle("Muted", parent=base["Normal"], fontSize=9, textColor=TEXT_MUTED, leading=13),
        "kpi_value": ParagraphStyle("KPIValue", parent=base["Normal"], fontSize=20, textColor=ACCENT, leading=22),
        "kpi_label": ParagraphStyle("KPILabel", parent=base["Normal"], fontSize=8, textColor=TEXT_MUTED),
    }


def _kpi_grid(styles, kpis: Dict[str, Any]) -> Table:
    portfolio = kpis.get("entity_portfolio", {})
    cities = kpis.get("city_coverage", {})

    cells = [
        (str(portfolio.get("total_tracked", "—")), "Entities Tracked"),
        (f"{portfolio.get('avg_composite_score') or '—'}/100", "Avg Composite Score"),
        (str(cities.get("active_on_district", "—")), "Active Markets"),
        (str(portfolio.get("international", "—")), "International Acts"),
    ]
    # Single row of 4 stacked value/label pairs
    value_row = [Paragraph(c[0], styles["kpi_value"]) for c in cells]
    label_row = [Paragraph(c[1], styles["kpi_label"]) for c in cells]
    table = Table([value_row, label_row], colWidths=[115] * 4)
    table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 14),
        ("LINEBELOW", (0, 1), (-1, 1), 0.5, DIVIDER),
    ]))
    return table


def _top_entities_table(styles, top_entities: List[Dict[str, Any]]) -> Table:
    header = ["#", "Name", "Type / Category", "Score", "Trend", "News (7d)"]
    rows = [header]
    if not top_entities:
        rows.append(["—", "No entities with live metrics yet", "", "", "", ""])
    else:
        for i, e in enumerate(top_entities, 1):
            rows.append([
                str(i),
                e.get("name", "—"),
                e.get("category") or e.get("type", "—"),
                f"{e.get('composite_score', '—')}",
                f"{e.get('google_trend', '—')}",
                f"{e.get('news_mentions_7d', 0)}",
            ])

    table = Table(rows, colWidths=[20, 160, 120, 45, 45, 60], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), TEXT_MUTED),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, DIVIDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _city_table(styles, cities: List[Dict[str, Any]]) -> Table:
    """Real city coverage data in place of a map graphic (no Mapbox integration exists yet)."""
    header = ["City", "Tier", "Status", "Music Market Score"]
    rows = [header]
    if not cities:
        rows.append(["—", "—", "No city data available", "—"])
    else:
        for c in cities:
            rows.append([
                c.get("name", "—"),
                f"Tier {c.get('tier', '—')}",
                "Active" if c.get("active_on_district") else "Expansion target",
                f"{c.get('music_market_size', '—')}",
            ])

    table = Table(rows, colWidths=[130, 60, 130, 130], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), TEXT_MUTED),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, DIVIDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def generate_executive_report_pdf(
    kpis: Dict[str, Any],
    top_cities: List[Dict[str, Any]],
    briefing_text: str,
    briefing_generated_at: str | None,
) -> bytes:
    """
    Builds the executive PDF report and returns it as raw bytes.
    kpis: response from GET /executive/kpis
    top_cities: list of city dicts (name, tier, active_on_district, music_market_size)
    briefing_text: AI-generated briefing text from GET /executive/briefing
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    styles = _styles()
    now = datetime.now(timezone.utc)

    story = []
    story.append(Paragraph("LiveIQ Executive Report", styles["title"]))
    story.append(Paragraph(
        f"District by Zomato — generated {now.strftime('%A, %d %B %Y at %H:%M UTC')}",
        styles["subtitle"],
    ))
    story.append(HRFlowable(width="100%", color=DIVIDER, thickness=0.75))
    story.append(Spacer(1, 12))

    story.append(_kpi_grid(styles, kpis))

    story.append(Paragraph("AI Executive Briefing", styles["h2"]))
    story.append(Paragraph(briefing_text or "AI briefing unavailable at generation time.", styles["body"]))
    if briefing_generated_at:
        story.append(Paragraph(f"Generated {briefing_generated_at}", styles["muted"]))

    story.append(Paragraph("Top Entities by Composite Score", styles["h2"]))
    story.append(_top_entities_table(styles, kpis.get("top_entities", [])))

    story.append(Paragraph("City Market Coverage", styles["h2"]))
    story.append(Paragraph(
        "No geographic mapping is configured yet (Mapbox integration pending) — "
        "showing real city coverage data instead of a map graphic.",
        styles["muted"],
    ))
    story.append(Spacer(1, 6))
    story.append(_city_table(styles, top_cities))

    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", color=DIVIDER, thickness=0.5))
    story.append(Paragraph(
        "Generated by LiveIQ — all figures sourced live from NeonDB at generation time. "
        "No hardcoded or estimated values are included except where explicitly noted.",
        styles["muted"],
    ))

    doc.build(story)
    return buf.getvalue()

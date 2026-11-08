"""
LiveIQ — Executive Intelligence Routes (Sprint 3C)
Real DB aggregates + Groq AI-generated briefings.

Endpoints:
  GET /executive/kpis        → Real-time KPI dashboard from NeonDB
  GET /executive/briefing    → AI-generated (Groq) executive summary
  GET /executive/portfolio   → Full entity portfolio health
"""

from typing import Optional
from datetime import datetime, timezone
import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select, func, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, run_queries
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.city import City
from app.core.config import settings
from app.services.latest_metric import latest_metric
from app.services.market_scope import Market, market_clause
from app.services.portfolio import stats_dict, stats_stmt, health_label
from app.services.market_scope import market_clause
from app.api.deps import get_current_user, require_roles
from app.models.user import User, UserRole

router = APIRouter()
logger = structlog.get_logger()


async def _kpis_payload(market: str) -> dict:
    lm = latest_metric()
    scope = market_clause(market)
    by_type_stmt = (
        select(Entity.entity_type, func.count(Entity.id).label("count"))
        .where(scope).group_by(Entity.entity_type).order_by(desc("count"), Entity.entity_type)
    )
    categories_stmt = (
        select(Entity.category, func.count(Entity.id).label("count"))
        .where(Entity.category.isnot(None), scope)
        .group_by(Entity.category).order_by(desc("count"), Entity.category).limit(8)
    )
    top_stmt = (
        select(Entity.name, Entity.entity_type, Entity.category, lm.composite_score,
               lm.google_trend_score, lm.news_mentions_7d, lm.data_completeness)
        .join(lm, Entity.id == lm.entity_id)
        .where(scope)
        .order_by(desc(lm.composite_score), Entity.name)
        .limit(5)
    )
    cities_stmt = select(func.count(City.id), func.count(City.id).filter(City.active_on_district.is_(True)))

    stats_rows, type_rows, cat_rows, top_rows, city_rows = await run_queries(
        stats_stmt(market), by_type_stmt, categories_stmt, top_stmt, cities_stmt
    )
    stats = stats_dict(stats_rows[0])
    total_cities, active_cities = (city_rows[0][0] or 0), (city_rows[0][1] or 0)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "entity_portfolio": {
            "total_tracked": stats["total"],
            "with_live_metrics": stats["scored"],
            "metrics_coverage_pct": stats["coverage_pct"],
            "avg_composite_score": stats["avg_score"],
            "by_type": {r[0]: r[1] for r in type_rows},
            "top_categories": [{"category": r[0], "count": r[1]} for r in cat_rows],
            "international": stats["international"],
            "indian": stats["domestic"],
        },
        "top_entities": [
            {"name": r[0], "type": r[1], "category": r[2],
             "composite_score": round(float(r[3]), 1), "google_trend": r[4],
             "news_mentions_7d": r[5], "data_completeness": r[6]}
            for r in top_rows
        ],
        "city_coverage": {
            "total_tracked": total_cities,
            "active_on_district": active_cities,
            "expansion_opportunities": total_cities - active_cities,
        },
        "data_freshness": {
            "last_metric_collection": "Celery worker runs every 6 hours",
            "entity_data_source": "Last.fm + YouTube + Google Trends + NewsAPI",
        },
    }


@router.get("/kpis", summary="Real-time executive KPI dashboard")
async def get_kpis(market: Market = "all", user: User = Depends(get_current_user)):
    """
    Aggregated KPIs (identical definitions to /dashboard/summary hero and
    /executive/portfolio - see app/services/portfolio.py): portfolio health,
    top performers, city coverage. `market` scopes all entity figures.
    """
    return await _kpis_payload(market)


async def _briefing_payload(market: str) -> dict:
    lm = latest_metric()
    scope = market_clause(market)
    top_stmt = (
        select(Entity.name, Entity.entity_type, Entity.category, lm.composite_score,
               lm.google_trend_score, lm.news_mentions_7d, lm.lastfm_listeners)
        .join(lm, Entity.id == lm.entity_id).where(scope)
        .order_by(desc(lm.composite_score), Entity.name).limit(5)
    )
    cities_stmt = (
        select(City.name, City.tier, City.music_market_size, City.active_on_district)
        .where(City.active_on_district.is_(True))
        .order_by(City.music_market_size.desc().nullslast(), City.name).limit(4)
    )
    stats_rows, top_entities, active_cities = await run_queries(stats_stmt(market), top_stmt, cities_stmt)
    stats = stats_dict(stats_rows[0])

    entity_lines = "\n".join(
        f"- {r[0]} ({r[2] or r[1]}): composite_score={round(r[3], 1)}, google_trend={r[4]}, news_7d={r[5]}"
        + (f", lfm_listeners={r[6]:,}" if r[6] else "")
        for r in top_entities
    )
    city_lines = "\n".join(
        f"- {r[0]} (Tier {r[1]}): music_market_score={r[2]}, active_on_district={r[3]}" for r in active_cities
    )

    prompt = f"""You are the LiveIQ intelligence system for District by Zomato, a premium live events platform in India.

Generate a concise executive briefing (3-4 short paragraphs) for the District leadership team based on the following real-time data:

ENTITY PORTFOLIO ({stats['total']} total, {stats['scored']} with live metrics):
{entity_lines if entity_lines else "No metric data yet — worker collecting now."}

ACTIVE MARKETS:
{city_lines if city_lines else "No city data available."}

Instructions:
- Write in a professional, data-driven tone
- Highlight the top trending entity and why they matter for District
- Note any booking opportunities based on the score data
- Keep it under 200 words
- Start with: "LiveIQ Weekly Pulse —"
"""

    degraded = False
    try:
        from app.services.groq_service import chat_completion
        briefing = await chat_completion(
            messages=[{"role": "user", "content": prompt}], max_tokens=300, temperature=0.4,
        )
    except Exception as e:
        logger.error("Groq briefing failed", error=type(e).__name__)
        degraded = True
        briefing = "AI briefing temporarily unavailable. Check Groq API key configuration."

    return {
        "briefing": briefing,
        "degraded": degraded,
        "market": market,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_context": {
            "entities_analyzed": len(top_entities),
            "active_cities": len(active_cities),
            "model": settings.GROQ_MODEL,
        },
    }


@router.get("/briefing", summary="AI-generated executive briefing (Groq)")
async def get_executive_briefing(market: Market = "all", user: User = Depends(get_current_user)):
    """Natural-language executive briefing synthesised from live DB data (Groq LLM)."""
    return await _briefing_payload(market)


@router.get("/portfolio", summary="Full entity portfolio health snapshot")
async def get_portfolio(
    entity_type: Optional[str] = Query(None, max_length=50),
    market: Market = "all",
    limit: int = Query(1000, ge=1, le=2000),
    offset: int = Query(0, ge=0, le=100000),
    user: User = Depends(get_current_user),
):
    """Entity portfolio ranked by latest composite score (unscored entities last), one row per entity."""
    lm = latest_metric()
    stmt = (
        select(Entity.id, Entity.name, Entity.entity_type, Entity.category, Entity.country,
               Entity.is_international, lm.composite_score, lm.google_trend_score,
               lm.news_mentions_7d, lm.time, lm.data_completeness, Entity.primary_market)
        .outerjoin(lm, Entity.id == lm.entity_id)
        .where(market_clause(market))
        .order_by(lm.composite_score.desc().nullslast(), Entity.name.asc(), Entity.id)
    )
    if entity_type:
        stmt = stmt.where(Entity.entity_type == entity_type)
    (rows,) = await run_queries(stmt)

    portfolio = []
    for i, r in enumerate(rows):
        score = r[6]
        portfolio.append({
            "rank": i + 1,
            "id": str(r[0]), "name": r[1], "type": r[2], "category": r[3], "country": r[4],
            "primary_market": r[11],
            "is_international": r[5] or False,
            "composite_score": round(float(score), 1) if score is not None else None,
            "google_trend_score": r[7], "news_mentions_7d": r[8],
            "health": health_label(score),
            "data_completeness": r[10],
            "last_updated": r[9].isoformat() if r[9] else None,
        })

    def _n(h):
        return sum(1 for p in portfolio if p["health"] == h)

    return {
        "portfolio": portfolio[offset:offset + limit],
        "total": len(portfolio),
        "offset": offset,
        "market": market,
        "with_scores": sum(1 for p in portfolio if p["composite_score"] is not None),
        "health_summary": {"strong": _n("Strong"), "good": _n("Good"), "needs_data": _n("Needs data"), "weak": _n("Weak")},
    }


@router.get("/report/pdf", summary="Download executive report as PDF")
async def get_executive_report_pdf(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.EXECUTIVE, UserRole.ANALYST)),
):
    """
    Generates a stakeholder-ready PDF: KPI summary, top entities, city
    coverage table (no map — no Mapbox integration exists yet), and the
    AI executive briefing. Reuses the same live-DB queries as /kpis and
    /briefing so the PDF and the dashboard never disagree with each other.
    """
    from app.services.ai.report_generator import generate_executive_report_pdf

    kpis = await _kpis_payload("all")
    briefing_response = await _briefing_payload("all")

    cities_result = await db.execute(
        select(City.name, City.tier, City.music_market_size, City.active_on_district)
        .order_by(City.music_market_size.desc().nullslast())
        .limit(12)
    )
    top_cities = [
        {"name": r[0], "tier": r[1], "music_market_size": r[2], "active_on_district": r[3]}
        for r in cities_result.all()
    ]

    pdf_bytes = generate_executive_report_pdf(
        kpis=kpis,
        top_cities=top_cities,
        briefing_text=briefing_response.get("briefing"),
        briefing_generated_at=briefing_response.get("generated_at"),
    )

    filename = f"liveiq-executive-report-{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.city import City
from app.services.latest_metric import latest_metric
from app.api.deps import get_current_user, require_roles
from app.models.user import User, UserRole

router = APIRouter()
logger = structlog.get_logger()


@router.get("/kpis", summary="Real-time executive KPI dashboard")
async def get_kpis(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Returns real-time aggregated KPIs from NeonDB:
    - Entity portfolio health
    - Top performing entities
    - City coverage
    - Market signal summary
    """
    # Total entities
    total_entities = await db.scalar(select(func.count(Entity.id)))

    # Entities with metrics
    entities_with_metrics = await db.scalar(
        select(func.count(func.distinct(EntityMetric.entity_id)))
    )

    # Average composite score (latest metric per entity)
    _latest = latest_metric()
    avg_score_result = await db.execute(
        select(func.avg(_latest.composite_score)).where(
            _latest.composite_score.isnot(None)
        )
    )
    avg_composite_score = avg_score_result.scalar()

    # Entities by type
    type_counts_result = await db.execute(
        select(Entity.entity_type, func.count(Entity.id).label("count"))
        .group_by(Entity.entity_type)
        .order_by(desc("count"))
    )
    entities_by_type = {row[0]: row[1] for row in type_counts_result.all()}

    # Entities by category
    category_counts_result = await db.execute(
        select(Entity.category, func.count(Entity.id).label("count"))
        .where(Entity.category.isnot(None))
        .group_by(Entity.category)
        .order_by(desc("count"))
        .limit(8)
    )
    top_categories = [{"category": r[0], "count": r[1]} for r in category_counts_result.all()]

    # Top 5 entities by composite score
    top_entities_result = await db.execute(
        select(Entity.name, Entity.entity_type, Entity.category, EntityMetric.composite_score,
               EntityMetric.google_trend_score, EntityMetric.news_mentions_7d)
        .join(EntityMetric, Entity.id == EntityMetric.entity_id)
        .where(EntityMetric.composite_score.isnot(None))
        .order_by(desc(EntityMetric.composite_score))
        .limit(5)
    )
    top_entities = [
        {
            "name": r[0],
            "type": r[1],
            "category": r[2],
            "composite_score": round(r[3], 1),
            "google_trend": r[4],
            "news_mentions_7d": r[5],
        }
        for r in top_entities_result.all()
    ]

    # City coverage
    total_cities = await db.scalar(select(func.count(City.id)))
    active_cities = await db.scalar(
        select(func.count(City.id)).where(City.active_on_district == True)  # noqa: E712
    )

    # International vs Indian entities
    intl_count = await db.scalar(
        select(func.count(Entity.id)).where(Entity.is_international == True)  # noqa: E712
    )
    indian_count = await db.scalar(
        select(func.count(Entity.id)).where(Entity.is_international == False)  # noqa: E712
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entity_portfolio": {
            "total_tracked": total_entities or 0,
            "with_live_metrics": entities_with_metrics or 0,
            "metrics_coverage_pct": round((entities_with_metrics or 0) / max(total_entities or 1, 1) * 100, 1),
            "avg_composite_score": round(avg_composite_score, 1) if avg_composite_score else None,
            "by_type": entities_by_type,
            "top_categories": top_categories,
            "international": intl_count or 0,
            "indian": indian_count or 0,
        },
        "top_entities": top_entities,
        "city_coverage": {
            "total_tracked": total_cities or 0,
            "active_on_district": active_cities or 0,
            "expansion_opportunities": (total_cities or 0) - (active_cities or 0),
        },
        "data_freshness": {
            "last_metric_collection": "Celery worker runs every 6 hours",
            "entity_data_source": "Last.fm + YouTube + Google Trends + NewsAPI",
        },
    }


@router.get("/briefing", summary="AI-generated executive briefing (Groq)")
async def get_executive_briefing(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Generates a natural language executive briefing using Groq Llama 3.3 70B.
    Pulls top entities + city data from DB and synthesizes into a District-style memo.
    """
    # Pull context data from DB
    top_result = await db.execute(
        select(Entity.name, Entity.entity_type, Entity.category, EntityMetric.composite_score,
               EntityMetric.google_trend_score, EntityMetric.news_mentions_7d, EntityMetric.lastfm_listeners)
        .join(EntityMetric, Entity.id == EntityMetric.entity_id)
        .where(EntityMetric.composite_score.isnot(None))
        .order_by(desc(EntityMetric.composite_score))
        .limit(5)
    )
    top_entities = top_result.all()

    cities_result = await db.execute(
        select(City.name, City.tier, City.music_market_size, City.active_on_district)
        .where(City.active_on_district == True)  # noqa: E712
        .order_by(City.music_market_size.desc())
        .limit(4)
    )
    active_cities = cities_result.all()

    total_entities = await db.scalar(select(func.count(Entity.id)))
    entities_with_metrics = await db.scalar(
        select(func.count(func.distinct(EntityMetric.entity_id)))
    )

    # Build context for AI
    entity_lines = "\n".join([
        f"- {r[0]} ({r[2] or r[1]}): composite_score={round(r[3], 1)}, "
        f"google_trend={r[4]}, news_7d={r[5]}, lfm_listeners={r[6]:,}" if r[6] else
        f"- {r[0]} ({r[2] or r[1]}): composite_score={round(r[3], 1)}, google_trend={r[4]}, news_7d={r[5]}"
        for r in top_entities
    ])
    city_lines = "\n".join([
        f"- {r[0]} (Tier {r[1]}): music_market_score={r[2]}, active_on_district={r[3]}"
        for r in active_cities
    ])

    prompt = f"""You are the LiveIQ intelligence system for District by Zomato, a premium live events platform in India.

Generate a concise executive briefing (3-4 short paragraphs) for the District leadership team based on the following real-time data:

ENTITY PORTFOLIO ({total_entities} total, {entities_with_metrics} with live metrics):
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

    try:
        from app.services.groq_service import chat_completion
        briefing = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.4,
        )
    except Exception as e:
        logger.error("Groq briefing failed", error=str(e))
        briefing = "AI briefing temporarily unavailable. Check Groq API key configuration."

    return {
        "briefing": briefing,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_context": {
            "entities_analyzed": len(top_entities),
            "active_cities": len(active_cities),
            "model": "llama-3.3-70b-versatile",
        },
    }


@router.get("/portfolio", summary="Full entity portfolio health snapshot")
async def get_portfolio(
    entity_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns the full entity portfolio ranked by composite score with health indicators."""
    stmt = (
        select(Entity, EntityMetric)
        .outerjoin(EntityMetric, Entity.id == EntityMetric.entity_id)
        .order_by(EntityMetric.composite_score.desc().nullslast(), Entity.name.asc())
    )
    if entity_type:
        stmt = stmt.where(Entity.entity_type == entity_type)

    result = await db.execute(stmt)
    rows = result.all()

    # Deduplicate — take highest metric per entity
    seen = {}
    for entity, metric in rows:
        eid = str(entity.id)
        if eid not in seen:
            seen[eid] = (entity, metric)
        elif metric and (seen[eid][1] is None or
                         (metric.composite_score or 0) > (seen[eid][1].composite_score or 0)):
            seen[eid] = (entity, metric)

    portfolio = []
    for i, (entity, metric) in enumerate(seen.values()):
        score = metric.composite_score if metric else None
        health = (
            "Strong" if score and score >= 40 else
            "Good" if score and score >= 25 else
            "Needs data" if score is None else
            "Weak"
        )
        portfolio.append({
            "rank": i + 1,
            "id": str(entity.id),
            "name": entity.name,
            "type": entity.entity_type,
            "category": entity.category,
            "country": entity.country,
            "is_international": entity.is_international or False,
            "composite_score": round(score, 1) if score else None,
            "google_trend_score": metric.google_trend_score if metric else None,
            "news_mentions_7d": metric.news_mentions_7d if metric else None,
            "health": health,
            "last_updated": metric.time.isoformat() if metric and metric.time else None,
        })

    # Re-rank after dedup
    portfolio.sort(key=lambda x: x["composite_score"] or -1, reverse=True)
    for i, p in enumerate(portfolio):
        p["rank"] = i + 1

    return {
        "portfolio": portfolio,
        "total": len(portfolio),
        "with_scores": sum(1 for p in portfolio if p["composite_score"] is not None),
        "health_summary": {
            "strong": sum(1 for p in portfolio if p["health"] == "Strong"),
            "good": sum(1 for p in portfolio if p["health"] == "Good"),
            "needs_data": sum(1 for p in portfolio if p["health"] == "Needs data"),
            "weak": sum(1 for p in portfolio if p["health"] == "Weak"),
        },
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

    kpis = await get_kpis(db, user)
    briefing_response = await get_executive_briefing(db, user)

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

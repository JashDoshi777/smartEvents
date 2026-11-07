"""
LiveIQ — Dashboard Summary Routes (Sprint 4)

Aggregates all dashboard-needed data into a single API call.

Endpoints:
  GET /dashboard/summary  → Full dashboard payload (entities, cities, briefing stub, alerts)
  GET /dashboard/alerts   → Live alerts derived from entity metrics + competitor feed
"""

from datetime import datetime, timezone
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, text, or_, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.city import City
from app.models.event import Event
from app.models.venue import Venue
from app.api.deps import get_current_user
from app.services.latest_metric import latest_metric
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()


@router.get("/summary", summary="Full dashboard data payload")
async def get_dashboard_summary(
    market: str = Query("all", pattern="^(all|india|global)$", description="Scope entity data to the Indian market, the rest of the world, or both"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Single endpoint that returns everything the dashboard needs.
    Frontend only calls this — no hardcoded data anywhere.
    """
    generated_at = datetime.now(timezone.utc).isoformat()
    EntityMetric = latest_metric()  # de-duplicated: newest snapshot per entity

    # Market scoping — applies to every entity-derived figure below.
    if market == "india":
        scope = Entity.primary_market == "India"
    elif market == "global":
        scope = or_(Entity.primary_market != "India", Entity.primary_market.is_(None))
    else:
        scope = true()

    # ── Hero counts ────────────────────────────────────────────────────────
    total_entities   = await db.scalar(select(func.count(Entity.id)).where(scope)) or 0
    total_cities     = await db.scalar(select(func.count(City.id))) or 0
    active_cities    = await db.scalar(
        select(func.count(City.id)).where(City.active_on_district == True)  # noqa: E712
    ) or 0
    total_events     = await db.scalar(select(func.count(Event.id))) or 0
    entities_w_metrics = await db.scalar(
        select(func.count(func.distinct(EntityMetric.entity_id)))
        .join(Entity, Entity.id == EntityMetric.entity_id).where(scope)
    ) or 0

    # ── Top trending entities (by composite score) ─────────────────────────
    trending_result = await db.execute(
        select(
            Entity.id,
            Entity.name,
            Entity.entity_type,
            Entity.category,
            Entity.country,
            Entity.is_international,
            EntityMetric.composite_score,
            EntityMetric.google_trend_score,
            EntityMetric.news_mentions_7d,
            EntityMetric.lastfm_listeners,
        )
        .join(EntityMetric, Entity.id == EntityMetric.entity_id)
        .where(EntityMetric.composite_score.isnot(None), scope)
        .order_by(desc(EntityMetric.composite_score))
        .limit(10)
    )
    trending_entities = [
        {
            "id":              str(r[0]),
            "name":            r[1],
            "type":            r[2],
            "category":        r[3],
            "country":         r[4],
            "is_international":r[5] or False,
            "composite_score": round(r[6], 1),
            "google_trend":    r[7],
            "news_mentions_7d":r[8],
            "listeners":       r[9],
        }
        for r in trending_result.all()
    ]

    # ── City heat index ────────────────────────────────────────────────────
    cities_result = await db.execute(
        select(
            City.name,
            City.tier,
            City.music_market_size,
            City.nightlife_score,
            City.active_on_district,
            City.population,
        )
        .order_by(City.music_market_size.desc().nullslast())
        .limit(8)
    )
    city_heat = [
        {
            "city":              r[0],
            "tier":              r[1],
            "music_score":       r[2],
            "nightlife_score":   r[3],
            "active_on_district":r[4] or False,
        }
        for r in cities_result.all()
    ]

    # ── Upcoming events (from events table) ────────────────────────────────
    events_result = await db.execute(
        select(
            Event.id,
            Event.title,
            Venue.city,
            Venue.name,
            Event.event_date,
            Event.category,
            Event.ticket_price_min,
            Event.ticket_price_max,
            Event.source,
        )
        .outerjoin(Venue, Event.venue_id == Venue.id)
        .where(Event.event_date.isnot(None))
        .order_by(Event.event_date.asc())
        .limit(6)
    )
    upcoming_events = [
        {
            "id":        str(r[0]),
            "name":      r[1],
            "city":      r[2],
            "venue":     r[3],
            "event_date":r[4].isoformat() if r[4] else None,
            "category":  r[5],
            "min_price": float(r[6]) if r[6] is not None else None,
            "max_price": float(r[7]) if r[7] is not None else None,
            "source":    r[8],
        }
        for r in events_result.all()
    ]

    # ── Category breakdown ─────────────────────────────────────────────────
    cat_result = await db.execute(
        select(Entity.category, func.count(Entity.id).label("count"))
        .where(Entity.category.isnot(None), scope)
        .group_by(Entity.category)
        .order_by(desc("count"))
        .limit(6)
    )
    category_breakdown = [
        {"category": r[0], "count": r[1]}
        for r in cat_result.all()
    ]

    # ── Entity type breakdown ──────────────────────────────────────────────
    type_result = await db.execute(
        select(Entity.entity_type, func.count(Entity.id).label("count"))
        .where(scope)
        .group_by(Entity.entity_type)
        .order_by(desc("count"))
    )
    type_breakdown = [
        {"type": r[0], "count": r[1]}
        for r in type_result.all()
    ]

    # ── Avg score ──────────────────────────────────────────────────────────
    avg_score = await db.scalar(
        select(func.avg(EntityMetric.composite_score))
        .join(Entity, Entity.id == EntityMetric.entity_id)
        .where(EntityMetric.composite_score.isnot(None), scope)
    )

    # ── International count ────────────────────────────────────────────────
    intl_count = await db.scalar(
        select(func.count(Entity.id)).where(Entity.is_international == True, scope)  # noqa: E712
    ) or 0

    return {
        "generated_at": generated_at,
        "hero": {
            "total_entities":       total_entities,
            "entities_with_metrics":entities_w_metrics,
            "total_cities":         total_cities,
            "active_cities":        active_cities,
            "expansion_targets":    total_cities - active_cities,
            "total_events":         total_events,
            "international_acts":   intl_count,
            "avg_composite_score":  round(avg_score, 1) if avg_score else None,
        },
        "trending_entities":  trending_entities,
        "city_heat":          city_heat,
        "upcoming_events":    upcoming_events,
        "category_breakdown": category_breakdown,
        "type_breakdown":     type_breakdown,
    }


@router.get("/alerts", summary="Live alerts from entity metrics and competitor data")
async def get_dashboard_alerts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Generates alert objects from:
    - Entities with unusually high google_trend vs composite gap (breakout signal)
    - Entities with high news_mentions_7d (buzz spike)
    - Cities with active_on_district=False but high music_market_size (gap opportunity)
    """
    alerts = []
    now = datetime.now(timezone.utc).isoformat()
    EntityMetric = latest_metric()  # de-duplicated: newest snapshot per entity

    # ── Breakout alerts: high google_trend relative to composite ───────────
    breakout_result = await db.execute(
        select(Entity.name, Entity.category, EntityMetric.composite_score,
               EntityMetric.google_trend_score, EntityMetric.news_mentions_7d)
        .join(EntityMetric, Entity.id == EntityMetric.entity_id)
        .where(
            EntityMetric.google_trend_score.isnot(None),
            EntityMetric.composite_score.isnot(None),
        )
        .order_by(desc(EntityMetric.google_trend_score))
        .limit(3)
    )
    for r in breakout_result.all():
        name, cat, score, trend, news = r
        if trend and score and trend > score:
            gap = round(trend - score, 1)
            alerts.append({
                "type":    "breakout",
                "title":   f"{name} showing breakout signals",
                "message": f"Google Trend score ({trend}) exceeds composite ({score}) by +{gap} pts — strong upcoming demand.",
                "entity":  name,
                "category":cat,
                "severity":"high",
                "ts":      now,
            })

    # ── News buzz alerts ───────────────────────────────────────────────────
    news_result = await db.execute(
        select(Entity.name, Entity.category, EntityMetric.news_mentions_7d,
               EntityMetric.composite_score)
        .join(EntityMetric, Entity.id == EntityMetric.entity_id)
        .where(
            EntityMetric.news_mentions_7d.isnot(None),
            EntityMetric.news_mentions_7d > 0,
        )
        .order_by(desc(EntityMetric.news_mentions_7d))
        .limit(2)
    )
    for r in news_result.all():
        name, cat, news, score = r
        alerts.append({
            "type":    "buzz",
            "title":   f"{name} in the news",
            "message": f"{news} news mentions in the last 7 days — consider fast-tracking booking.",
            "entity":  name,
            "category":cat,
            "severity":"medium",
            "ts":      now,
        })

    # ── Market gap alerts: high-score cities not on District ───────────────
    gap_result = await db.execute(
        select(City.name, City.tier, City.music_market_size)
        .where(
            City.active_on_district == False,  # noqa: E712
            City.music_market_size.isnot(None),
        )
        .order_by(City.music_market_size.desc())
        .limit(2)
    )
    for r in gap_result.all():
        city, tier, score = r
        alerts.append({
            "type":    "opportunity",
            "title":   f"{city} market gap detected",
            "message": f"Tier-{tier} city with music score {score} — no active District events. Competitor window open.",
            "entity":  None,
            "category":"Market",
            "severity":"medium",
            "ts":      now,
        })

    # ── Fallback if no data ────────────────────────────────────────────────
    if not alerts:
        alerts.append({
            "type":    "info",
            "title":   "No alerts yet",
            "message": "Run the entity metrics worker to generate live breakout and buzz alerts.",
            "entity":  None,
            "category":None,
            "severity":"low",
            "ts":      now,
        })

    return {
        "alerts":       alerts,
        "total":        len(alerts),
        "generated_at": now,
    }

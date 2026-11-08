"""
LiveIQ — Trends Routes
Real DB-backed trend intelligence. Every listing accepts `market=india|global|all`
and ranks the LATEST scored snapshot per entity (one row per entity).
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db, run_queries
from app.core.sql import ilike_contains
from app.models.entity import Entity
from app.models.event import Event
from app.models.user import User
from app.models.venue import Venue
from app.services.latest_metric import latest_metric, score_fields, trend_direction
from app.services.market_scope import Market, market_clause

router = APIRouter()
logger = structlog.get_logger()


@router.get("/momentum", summary="Top risers/fallers by real weekly Wikipedia attention history")
async def get_momentum(
    market: Market = "india",
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Momentum = last complete ISO week's Wikipedia pageviews vs the mean of the 4 weeks before it (NULL when that
    baseline is under 200 views/week). Includes robust z-score against the entity's own 26-week history."""
    from app.services.momentum import momentum_for_market
    return {"market": market, **await momentum_for_market(db, market_clause(market), limit)}


@router.get("/breakout", summary="Top entities by composite score")
async def get_breakouts(
    category: Optional[str] = Query(None, max_length=100, description="Filter by: Bollywood, Punjabi Pop, K-Pop..."),
    entity_type: Optional[str] = Query(None, max_length=50, description="Filter by: artist, comedian, sports_team..."),
    is_international: Optional[bool] = Query(None),
    market: Market = "all",
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Top entities ranked by latest composite score. If no scored entity matches
    the filters, falls back to a verified/active ordering with null scores
    (same market/category/type/international filters apply to the fallback).
    """
    lm = latest_metric()

    def _filters(stmt):
        stmt = stmt.where(market_clause(market))
        if category:
            stmt = stmt.where(ilike_contains(Entity.category, category))
        if entity_type:
            stmt = stmt.where(Entity.entity_type == entity_type)
        if is_international is not None:
            stmt = stmt.where(Entity.is_international == is_international)
        return stmt

    scored_stmt = _filters(select(Entity, lm).join(lm, Entity.id == lm.entity_id).where(lm.composite_score.isnot(None))).order_by(
        lm.composite_score.desc(), Entity.name, Entity.id
    ).limit(limit)
    fallback_stmt = _filters(select(Entity).where(Entity.status == "active")).order_by(
        Entity.is_verified.desc().nullslast(), Entity.is_active_on_district.desc().nullslast(), Entity.name, Entity.id
    ).limit(limit)
    rows, fallback_rows = await run_queries(scored_stmt, fallback_stmt)

    scored = [
        {
            "entity_id": str(e.id), "name": e.name, "entity_type": e.entity_type,
            "category": e.category, "country": e.country,
            **score_fields(m.composite_score, m.score_confidence, m.signals_used),
            "trend_direction": trend_direction(m.trend_velocity),
            "lastfm_listeners": m.lastfm_listeners,
            "news_mentions_7d": m.news_mentions_7d,
            "google_trend_score": m.google_trend_score,
            "data_completeness": m.data_completeness,
            "last_updated": m.time.isoformat() if m.time else None,
        }
        for e, m in rows
    ]
    if not scored:
        scored = [
            {
                "entity_id": str(r[0].id), "name": r[0].name, "entity_type": r[0].entity_type,
                "category": r[0].category, "country": r[0].country,
                "composite_score": None, "trend_direction": "pending",
                "lastfm_listeners": None, "news_mentions_7d": None, "google_trend_score": None,
                "data_completeness": None, "last_updated": None,
            }
            for r in fallback_rows
        ]

    return {
        "predictions": scored,
        "total": len(scored),
        "market": market,
        "has_live_scores": any(p["composite_score"] is not None for p in scored),
        "note": "Composite v3: per-type weighted score over VERIFIED signals only (YouTube, Wikipedia, Last.fm for artists, anchored Google Trends, strictly filtered news). Entities with too little verified data are unrated and never ranked.",
    }


@router.get("/viral", summary="Entities with highest news + social spike")
async def get_viral_signals(
    market: Market = "all",
    limit: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Entities with the most news mentions in the last 7 days (only entities with > 0 mentions)."""
    lm = latest_metric()
    stmt = (
        select(Entity, lm)
        .join(lm, Entity.id == lm.entity_id)
        .where(lm.news_mentions_7d > 0, market_clause(market))
        .order_by(desc(lm.news_mentions_7d), lm.composite_score.desc().nullslast(), Entity.name, Entity.id)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    signals = [
        {
            "entity_id": str(e.id), "name": e.name, "entity_type": e.entity_type,
            "news_mentions_7d": m.news_mentions_7d,
            "google_trend_score": m.google_trend_score,
            **score_fields(m.composite_score, m.score_confidence, m.signals_used),
            "sentiment_compound": m.sentiment_compound,
        }
        for e, m in rows
    ]
    if not signals:
        return {"signals": [], "total": 0, "market": market,
                "message": "No metrics collected yet. Celery workers will populate this data."}
    return {"signals": signals, "total": len(signals), "market": market}


@router.get("/genre/{city}", summary="Top genres by city")
async def get_genre_momentum(
    city: str,
    market: Market = "all",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Genre distribution for a city: entities that have events at venues in that
    city, grouped by genre. When the city has no event history the global
    genre distribution is returned instead and `scope` says so (the previous
    version ignored `city` entirely).
    """
    city = city.strip()[:100]
    city_stmt = (
        select(Entity.genre, func.count(func.distinct(Entity.id)).label("count"))
        .join(Event, Event.entity_id == Entity.id)
        .join(Venue, Venue.id == Event.venue_id)
        .where(Entity.genre.isnot(None), ilike_contains(Venue.city, city), market_clause(market))
        .group_by(Entity.genre).order_by(desc("count"), Entity.genre).limit(10)
    )
    global_stmt = (
        select(Entity.genre, func.count(Entity.id).label("count"))
        .where(Entity.genre.isnot(None), market_clause(market))
        .group_by(Entity.genre).order_by(desc("count"), Entity.genre).limit(10)
    )
    city_rows, global_rows = await run_queries(city_stmt, global_stmt)
    rows, scope = (city_rows, "city") if city_rows else (global_rows, "global_fallback")

    return {
        "city": city,
        "scope": scope,
        "market": market,
        "genres": [{"genre": r[0], "entity_count": r[1]} for r in rows],
        "note": "City scope = entities with events at venues in the city; falls back to the global distribution when the city has none.",
    }


@router.get("/regional", summary="Regional culture shifts across India")
async def get_regional_trends(
    market: Market = "all",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Entity distribution by country."""
    stmt = (
        select(Entity.country, func.count(Entity.id).label("count"))
        .where(Entity.country.isnot(None), market_clause(market))
        .group_by(Entity.country)
        .order_by(desc("count"), Entity.country)
    )
    rows = (await db.execute(stmt)).all()
    return {
        "regions": [{"country": r[0], "entity_count": r[1]} for r in rows],
        "total_entities": sum(r[1] for r in rows),
        "market": market,
    }

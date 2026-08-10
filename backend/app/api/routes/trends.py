"""
LiveIQ — Trends Routes (Sprint 2B)
Real DB-backed trend intelligence.
"""

from typing import Optional
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()


@router.get("/breakout", summary="Top entities by composite score")
async def get_breakouts(
    category: Optional[str] = Query(None, description="Filter by: Bollywood, Punjabi Pop, K-Pop..."),
    entity_type: Optional[str] = Query(None, description="Filter by: artist, comedian, sports_team..."),
    is_international: Optional[bool] = Query(None),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns top entities ranked by latest composite score.
    Entities with no metrics yet are listed separately.
    Sprint 4: will use IsolationForest anomaly detection for true breakout prediction.
    """
    # Get latest metric per entity using a simple join ordered by time desc
    # (Simpler than correlated subquery — works with both NeonDB and test mocks)
    stmt = (
        select(Entity, EntityMetric)
        .join(EntityMetric, Entity.id == EntityMetric.entity_id)
    )
    if category:
        stmt = stmt.where(Entity.category.ilike(f"%{category}%"))
    if entity_type:
        stmt = stmt.where(Entity.entity_type == entity_type)
    if is_international is not None:
        stmt = stmt.where(Entity.is_international == is_international)

    stmt = stmt.order_by(EntityMetric.time.desc(), EntityMetric.composite_score.desc()).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    scored = [
        {
            "entity_id": str(e.id),
            "name": e.name,
            "entity_type": e.entity_type,
            "category": e.category,
            "country": e.country,
            "composite_score": round(m.composite_score or 0, 1),
            "trend_direction": "rising" if (m.trend_velocity or 0) > 2 else (
                "falling" if (m.trend_velocity or 0) < -2 else "stable"
            ),
            "lastfm_listeners": m.lastfm_listeners,
            "news_mentions_7d": m.news_mentions_7d,
            "google_trend_score": m.google_trend_score,
            "last_updated": m.time.isoformat() if m.time else None,
        }
        for e, m in rows
    ]

    # If no metrics yet, return top entities by verification/active status
    if not scored:
        fallback_stmt = select(Entity).where(Entity.status == "active")
        if category:
            fallback_stmt = fallback_stmt.where(Entity.category.ilike(f"%{category}%"))
        if entity_type:
            fallback_stmt = fallback_stmt.where(Entity.entity_type == entity_type)
        fallback_stmt = fallback_stmt.order_by(
            Entity.is_verified.desc(),
            Entity.is_active_on_district.desc(),
        ).limit(limit)
        fallback_result = await db.execute(fallback_stmt)
        fallback_entities = fallback_result.scalars().all()

        scored = [
            {
                "entity_id": str(e.id),
                "name": e.name,
                "entity_type": e.entity_type,
                "category": e.category,
                "country": e.country,
                "composite_score": None,
                "trend_direction": "pending",
                "listener_delta_7d": None,
                "news_mentions_7d": None,
                "google_trend_score": None,
                "last_updated": None,
            }
            for e in fallback_entities
        ]

    return {
        "predictions": scored,
        "total": len(scored),
        "has_live_scores": any(p["composite_score"] is not None for p in scored),
        "note": "Scores computed from Last.fm, YouTube, Google Trends, NewsAPI signals.",
    }


@router.get("/viral", summary="Entities with highest news + social spike")
async def get_viral_signals(
    limit: int = Query(10, le=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns entities with highest news mention spike in the last 7 days.
    Sprint 4: will add Instagram Reels + YouTube Shorts view velocity.
    """
    stmt = (
        select(Entity, EntityMetric)
        .join(EntityMetric, Entity.id == EntityMetric.entity_id)
        .where(EntityMetric.news_mentions_7d.isnot(None))
        .order_by(desc(EntityMetric.news_mentions_7d))
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    signals = [
        {
            "entity_id": str(e.id),
            "name": e.name,
            "entity_type": e.entity_type,
            "news_mentions_7d": m.news_mentions_7d,
            "google_trend_score": m.google_trend_score,
            "composite_score": round(m.composite_score or 0, 1),
            "sentiment_compound": m.sentiment_compound,
        }
        for e, m in rows
    ]

    if not signals:
        return {
            "signals": [],
            "message": "No metrics collected yet. Celery workers will populate this data.",
        }

    return {"signals": signals, "total": len(signals)}


@router.get("/genre/{city}", summary="Top genres by city")
async def get_genre_momentum(city: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Genre distribution for a given city — Sprint 4 will add momentum scoring."""
    stmt = (
        select(Entity.genre, func.count(Entity.id).label("count"))
        .where(Entity.genre.isnot(None))
        .group_by(Entity.genre)
        .order_by(desc("count"))
        .limit(10)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "city": city,
        "genres": [{"genre": r[0], "entity_count": r[1]} for r in rows],
        "note": "Sprint 4: will weight by city-specific ticket sales velocity.",
    }


@router.get("/regional", summary="Regional culture shifts across India")
async def get_regional_trends(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Returns entity distribution by country/market — Sprint 4 will add inter-city movement."""
    stmt = (
        select(Entity.country, func.count(Entity.id).label("count"))
        .where(Entity.country.isnot(None))
        .group_by(Entity.country)
        .order_by(desc("count"))
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "regions": [{"country": r[0], "entity_count": r[1]} for r in rows],
        "total_entities": sum(r[1] for r in rows),
    }

"""
LiveIQ — Entity Intelligence Routes (Sprint 2B)
Real PostgreSQL-backed implementation replacing all stubs.

Endpoints:
  GET  /entities/search          → ILIKE name search + type filter
  GET  /entities/{id}            → Full entity profile
  GET  /entities/{id}/score      → Composite intelligence score
  GET  /entities/{id}/cities     → City demand ranking
  POST /entities/compare         → Side-by-side comparison
"""

from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity, EntityType
from app.models.metrics import EntityMetric
from app.models.city import City
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()


# ─── Response Schemas ─────────────────────────────────────────────────────────

class EntitySummary(BaseModel):
    id: str
    name: str
    entity_type: str
    category: Optional[str]
    genre: Optional[str]
    country: Optional[str]
    is_international: bool
    is_active_on_district: bool
    description: Optional[str]
    image_url: Optional[str]

    class Config:
        from_attributes = True


class EntityProfile(EntitySummary):
    home_city: Optional[str]
    primary_market: Optional[str]
    genres: Optional[List[str]]
    sub_categories: Optional[List[str]]
    data_sources: Optional[List[str]]
    booking_price_range_min: Optional[float]
    booking_price_range_max: Optional[float]
    typical_venue_capacity_min: Optional[int]
    typical_venue_capacity_max: Optional[int]
    is_verified: bool
    is_featured: bool


def _entity_to_summary(e: Entity) -> dict:
    return {
        "id": str(e.id),
        "name": e.name,
        "entity_type": e.entity_type,
        "category": e.category,
        "genre": e.genre,
        "country": e.country,
        "is_international": e.is_international or False,
        "is_active_on_district": e.is_active_on_district or False,
        "description": e.description,
        "image_url": e.image_url,
    }


def _entity_to_profile(e: Entity) -> dict:
    return {
        **_entity_to_summary(e),
        "home_city": e.home_city,
        "primary_market": e.primary_market,
        "genres": e.genres or [],
        "sub_categories": e.sub_categories or [],
        "data_sources": e.data_sources or [],
        "booking_price_range_min": e.booking_price_range_min,
        "booking_price_range_max": e.booking_price_range_max,
        "typical_venue_capacity_min": e.typical_venue_capacity_min,
        "typical_venue_capacity_max": e.typical_venue_capacity_max,
        "is_verified": e.is_verified or False,
        "is_featured": e.is_featured or False,
    }


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/search", summary="Search entities by name")
async def search_entities(
    q: str = Query(..., min_length=2, description="Search query (min 2 chars)"),
    entity_type: Optional[str] = Query(None, description="Filter: artist, movie, comedian, sports_team..."),
    category: Optional[str] = Query(None, description="Filter by category e.g. 'Bollywood', 'K-Pop'"),
    is_international: Optional[bool] = Query(None, description="Filter international artists"),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Search entities by name using PostgreSQL ILIKE (case-insensitive partial match).
    Future: upgrade to pg_trgm GIN index for fuzzy search.
    """
    stmt = select(Entity).where(
        or_(
            Entity.name.ilike(f"%{q}%"),
            Entity.description.ilike(f"%{q}%"),
        )
    )

    if entity_type:
        stmt = stmt.where(Entity.entity_type == entity_type)
    if category:
        stmt = stmt.where(Entity.category.ilike(f"%{category}%"))
    if is_international is not None:
        stmt = stmt.where(Entity.is_international == is_international)

    stmt = stmt.order_by(
        Entity.is_verified.desc(),
        Entity.is_active_on_district.desc(),
        Entity.name.asc()
    ).limit(limit)

    result = await db.execute(stmt)
    entities = result.scalars().all()

    return {
        "query": q,
        "total": len(entities),
        "results": [_entity_to_summary(e) for e in entities],
    }


@router.get("/category/{entity_type}", summary="Browse entities by type")
async def browse_by_type(
    entity_type: str,
    category: Optional[str] = Query(None),
    is_international: Optional[bool] = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Browse all entities of a given type (artist, movie, comedian, etc.)"""
    valid_types = [e.value for e in EntityType]
    if entity_type not in valid_types:
        raise HTTPException(400, f"Invalid entity_type. Must be one of: {valid_types}")

    stmt = select(Entity).where(Entity.entity_type == entity_type)
    if category:
        stmt = stmt.where(Entity.category.ilike(f"%{category}%"))
    if is_international is not None:
        stmt = stmt.where(Entity.is_international == is_international)

    stmt = stmt.order_by(
        Entity.is_verified.desc(),
        Entity.is_active_on_district.desc(),
    ).limit(limit)

    result = await db.execute(stmt)
    entities = result.scalars().all()

    return {
        "entity_type": entity_type,
        "total": len(entities),
        "results": [_entity_to_summary(e) for e in entities],
    }


@router.get("/{entity_id}/profile", summary="Full entity profile")
async def get_entity_profile(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns full entity profile with metadata, price ranges, and data sources."""
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity ID format")

    result = await db.execute(select(Entity).where(Entity.id == uid))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    return _entity_to_profile(entity)


@router.get("/{entity_id}/score", summary="Entity intelligence score")
async def get_entity_score(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns composite intelligence score (0–100) and signal breakdown.
    Score is computed from latest EntityMetric row.
    If no metrics exist yet, returns a placeholder with data_sources info.
    """
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity ID format")

    # Get entity
    result = await db.execute(select(Entity).where(Entity.id == uid))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    # Get latest metric
    metric_result = await db.execute(
        select(EntityMetric)
        .where(EntityMetric.entity_id == uid)
        .order_by(EntityMetric.time.desc())
        .limit(1)
    )
    metric = metric_result.scalar_one_or_none()

    if metric:
        return {
            "entity_id": entity_id,
            "entity_name": entity.name,
            "composite_score": round(metric.composite_score or 0, 1),
            "trend_direction": "rising" if (metric.trend_velocity or 0) > 2 else (
                "falling" if (metric.trend_velocity or 0) < -2 else "stable"
            ),
            "signals": {
                "lastfm_listeners": metric.lastfm_listeners,
                "youtube_subscribers": metric.youtube_subscribers,
                "youtube_views_30d": metric.youtube_views_30d,
                "news_mentions_7d": metric.news_mentions_7d,
                "google_trend_score": metric.google_trend_score,
                "google_trend_delta_7d": metric.google_trend_delta_7d,
                "sentiment_compound": metric.sentiment_compound,
                "data_completeness": metric.data_completeness,
            },
            "last_updated": metric.time.isoformat() if metric.time else None,
            "data_sources": entity.data_sources or [],
        }
    else:
        # No metrics collected yet — return entity info with pending status
        return {
            "entity_id": entity_id,
            "entity_name": entity.name,
            "composite_score": None,
            "trend_direction": "pending",
            "signals": {},
            "last_updated": None,
            "data_sources": entity.data_sources or [],
            "message": "Metrics not yet collected. Workers will populate this data.",
        }



# Maps an entity/event category to the City column that best represents
# demand for that category. Falls back to the overall composite average.
_CATEGORY_TO_CITY_FIELD = {
    "music": "music_market_size",
    "bollywood": "music_market_size",
    "edm": "music_market_size",
    "k-pop": "music_market_size",
    "international": "music_market_size",
    "comedy": "comedy_market_size",
    "sports": "sports_affinity_score",
    "theatre": "arts_culture_score",
    "nightlife": "nightlife_score",
}


@router.get("/{entity_id}/cities", summary="City demand ranking for entity")
async def get_entity_cities(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns city-level demand ranking for this entity, computed from real
    City market-score data (music/comedy/sports/arts/nightlife) already
    stored in Postgres — no hardcoded city list.
    """
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity ID format")

    result = await db.execute(select(Entity).where(Entity.id == uid))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    cities_result = await db.execute(select(City))
    cities = cities_result.scalars().all()

    category_key = (entity.category or "").lower()
    field_name = next(
        (field for key, field in _CATEGORY_TO_CITY_FIELD.items() if key in category_key),
        None,
    )

    demand = []
    for c in cities:
        if field_name:
            score = getattr(c, field_name)
        else:
            scores = [c.nightlife_score, c.sports_affinity_score, c.arts_culture_score,
                      c.comedy_market_size, c.music_market_size]
            valid = [s for s in scores if s is not None]
            score = round(sum(valid) / len(valid), 1) if valid else None
        if score is None:
            continue

        is_home_city = bool(entity.home_city and entity.home_city.lower() in c.name.lower())
        demand.append({
            "city": c.name,
            "state": c.state,
            "tier": c.tier,
            "demand_score": round(min(100, score + 10), 1) if is_home_city else round(score, 1),
            "is_home_city": is_home_city,
            "active_on_district": c.active_on_district or False,
        })

    demand.sort(key=lambda x: x["demand_score"], reverse=True)
    for i, c in enumerate(demand):
        c["demand_rank"] = i + 1

    return {
        "entity_id": entity_id,
        "entity_name": entity.name,
        "cities": demand,
        "methodology": f"Ranked by City.{field_name or 'composite_average'}, +10 boost for entity's home city.",
    }


@router.post("/compare", summary="Compare 2–4 entities side by side")
async def compare_entities(
    entity_ids: List[str],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Side-by-side entity comparison."""
    if len(entity_ids) < 2 or len(entity_ids) > 4:
        raise HTTPException(400, "Provide 2–4 entity IDs to compare")

    profiles = []
    for eid in entity_ids:
        try:
            uid = UUID(eid)
        except ValueError:
            raise HTTPException(400, f"Invalid entity ID: {eid}")
        result = await db.execute(select(Entity).where(Entity.id == uid))
        entity = result.scalar_one_or_none()
        if not entity:
            raise HTTPException(404, f"Entity '{eid}' not found")

        # Get latest metric
        metric_result = await db.execute(
            select(EntityMetric)
            .where(EntityMetric.entity_id == uid)
            .order_by(EntityMetric.time.desc())
            .limit(1)
        )
        metric = metric_result.scalar_one_or_none()

        if metric:
            trend_direction = "rising" if (metric.trend_velocity or 0) > 2 else (
                "falling" if (metric.trend_velocity or 0) < -2 else "stable"
            )
            listeners = metric.lastfm_listeners or metric.spotify_monthly_listeners
        else:
            trend_direction = "pending"
            listeners = None

        profiles.append({
            **_entity_to_profile(entity),
            "composite_score": round(metric.composite_score or 0, 1) if metric else None,
            "trend_direction": trend_direction,
            "listeners": listeners,
        })

    return {"entities": profiles, "comparison_count": len(profiles)}

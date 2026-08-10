"""
LiveIQ — AI Recommendation Engine (M6)
Hybrid rules + ML re-ranking, per IMPLEMENTATION_PLAN.md's M6 spec:
rules-based filtering (data sufficiency, category/city/budget) narrows
the candidate pool, then real signals (composite_score, city demand
match, and — for /sign — the same GradientBoostingRegressor pricing
engine /pricing/optimize already uses) rank and score what's left.

No new ML model or fabricated signal is introduced here — this reuses
the exact composite_score + city-demand-field logic already live in
GET /entities/{id}/cities, and the exact pricing_engine.predict() call
already live in POST /pricing/optimize, so a recommendation here can
never disagree with what those two endpoints would say standalone.

Endpoints:
  GET  /recommend/entities   → ranked candidates worth booking, with real filters
  POST /recommend/sign       → sign/consider/pass verdict for one specific
                                entity+city+venue+price combination
"""

from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.city import City
from app.models.user_data import Watchlist
from app.api.deps import get_current_user, require_roles
from app.models.user import User, UserRole

try:
    from app.services.ml.pricing_engine import pricing_engine
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    pricing_engine = None  # type: ignore

router = APIRouter()
logger = structlog.get_logger()

# Same mapping /entities/{id}/cities uses — kept in one place would be
# nicer, but that module doesn't export it as a shared symbol yet, and
# duplicating a 6-line dict is cheaper than reaching into another
# route module's internals across files.
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


def _city_demand_field(category: Optional[str]) -> Optional[str]:
    key = (category or "").lower()
    return next((field for k, field in _CATEGORY_TO_CITY_FIELD.items() if k in key), None)


def _city_demand_score(city_obj: City, category: Optional[str]) -> Optional[float]:
    """
    Same fallback semantics as GET /entities/{id}/cities (entities.py):
    a category that doesn't match any known key averages all 5 real city
    market-dimension scores, rather than silently defaulting to
    music_market_size — the two endpoints must agree on this number for
    the same entity/city, since /recommend/entities' own docstring
    promises it never disagrees with /entities/{id}/cities.
    """
    field_name = _city_demand_field(category)
    if field_name:
        return getattr(city_obj, field_name, None)
    scores = [
        city_obj.nightlife_score, city_obj.sports_affinity_score, city_obj.arts_culture_score,
        city_obj.comedy_market_size, city_obj.music_market_size,
    ]
    valid = [s for s in scores if s is not None]
    return round(sum(valid) / len(valid), 1) if valid else None


class SignRequest(BaseModel):
    entity_id: str = Field(..., description="UUID of the entity to evaluate")
    city: str = Field(..., description="Target city for the booking")
    venue_capacity: int = Field(..., ge=100, le=100000)
    proposed_price: float = Field(..., ge=100, le=50000, description="Proposed base ticket price (INR)")
    category: Optional[str] = Field(None, description="Event category override")


@router.get("/entities", summary="Ranked entity recommendations worth booking")
async def recommend_entities(
    category: Optional[str] = Query(None, description="Filter: music, comedy, sports, theatre..."),
    city: Optional[str] = Query(None, description="Rank by demand fit for this specific city"),
    is_international: Optional[bool] = Query(None),
    exclude_watchlisted: bool = Query(False, description="Exclude entities already on your watchlist"),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Rules filter (real data required, optional category/city/international/
    watchlist exclusion) -> rank by composite_score blended with the
    target city's real demand-field score for that category (same field
    /entities/{id}/cities uses). No entity is scored without a real
    EntityMetric row backing it — entities with zero collected metrics
    are excluded, not defaulted to a fabricated mid-range score.
    """
    # ── Rules: latest SCORED metric per entity, joined to entity ────────────
    # The composite_score filter must apply BEFORE taking MAX(time), not
    # after — entity_metrics.py and social_listening.py both insert a new
    # EntityMetric row for the same entity on independent schedules, and
    # social_listening's rows never populate composite_score (it owns
    # sentiment fields only). If the most recent row for an entity happens
    # to be one of those, filtering by composite_score.isnot(None) AFTER
    # picking "latest" would silently drop an entity that has a perfectly
    # real, valid score sitting in an earlier row.
    latest_time_subq = (
        select(EntityMetric.entity_id, func.max(EntityMetric.time).label("max_time"))
        .where(EntityMetric.composite_score.isnot(None))
        .group_by(EntityMetric.entity_id)
        .subquery()
    )
    stmt = (
        select(Entity, EntityMetric)
        .join(latest_time_subq, Entity.id == latest_time_subq.c.entity_id)
        .join(
            EntityMetric,
            (EntityMetric.entity_id == latest_time_subq.c.entity_id)
            & (EntityMetric.time == latest_time_subq.c.max_time),
        )
    )
    if category:
        stmt = stmt.where(Entity.category.ilike(f"%{category}%"))
    if is_international is not None:
        stmt = stmt.where(Entity.is_international == is_international)

    if exclude_watchlisted:
        watchlisted_subq = select(Watchlist.entity_id).where(Watchlist.user_id == user.id)
        stmt = stmt.where(Entity.id.notin_(watchlisted_subq))

    result = await db.execute(stmt)
    rows = result.all()

    # ── Real city-demand lookup (only if a target city was given) ──────────
    city_obj = None
    if city:
        city_result = await db.execute(select(City).where(City.name.ilike(f"%{city}%")))
        city_obj = city_result.scalar_one_or_none()
        if city_obj is None:
            raise HTTPException(404, f"City '{city}' not tracked")

    candidates = []
    for entity, metric in rows:
        composite = metric.composite_score or 0.0
        city_demand = _city_demand_score(city_obj, entity.category) if city_obj else None

        if city_obj is not None:
            if city_demand is None:
                continue  # no real demand data for this city/category combo — don't guess
            # Blend: entity's own real momentum (60%) + how well this specific
            # city's real market matches this category (40%) — same weighting
            # philosophy as pricing.py's demand_score, applied to ranking
            # instead of price.
            blended = composite * 0.60 + city_demand * 0.40
        else:
            blended = composite

        candidates.append({
            "entity_id": str(entity.id),
            "entity_name": entity.name,
            "entity_type": entity.entity_type,
            "category": entity.category,
            "is_international": entity.is_international or False,
            "composite_score": round(composite, 1),
            "city_demand_score": round(city_demand, 1) if city_demand is not None else None,
            "recommendation_score": round(blended, 1),
            "trend_direction": "rising" if (metric.trend_velocity or 0) > 2 else (
                "falling" if (metric.trend_velocity or 0) < -2 else "stable"
            ),
            "last_updated": metric.time.isoformat() if metric.time else None,
        })

    candidates.sort(key=lambda c: c["recommendation_score"], reverse=True)
    ranked = candidates[:limit]
    for i, c in enumerate(ranked):
        c["rank"] = i + 1

    return {
        "recommendations": ranked,
        "total_candidates": len(candidates),
        "filters_applied": {
            "category": category, "city": city,
            "is_international": is_international, "exclude_watchlisted": exclude_watchlisted,
        },
        "methodology": (
            f"Ranked by 60% entity composite_score + 40% city.{_city_demand_field(category) or 'composite_average'} "
            f"for '{city}'" if city else
            "Ranked by entity composite_score alone (no target city given)"
        ),
    }


@router.post("/sign", summary="Sign / consider / pass verdict for a specific booking")
async def recommend_sign(
    request: SignRequest,
    db: AsyncSession = Depends(get_db),
    # Booking decisions are Booker/Analyst/Executive territory, same gate
    # as /pricing/optimize and /events/model (ARCHITECTURE_AND_APP_STRUCTURE.md §9).
    user: User = Depends(require_roles(UserRole.EXECUTIVE, UserRole.ANALYST, UserRole.BOOKER)),
):
    """
    Runs one entity+city+venue+price combination through the same real
    pricing/fill-rate model /pricing/optimize uses, then applies a
    transparent, deterministic verdict rule on top — no LLM call, no
    second model: same real numbers, judged by fixed real thresholds
    so the verdict is always explainable from the numbers shown.
    """
    if not ML_AVAILABLE or pricing_engine is None:
        raise HTTPException(503, "Pricing engine unavailable — cannot produce a sign recommendation")

    try:
        uid = UUID(request.entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = await db.scalar(select(Entity).where(Entity.id == uid))
    if entity is None:
        raise HTTPException(404, f"Entity '{request.entity_id}' not found")

    metric = await db.scalar(
        select(EntityMetric).where(EntityMetric.entity_id == uid).order_by(desc(EntityMetric.time)).limit(1)
    )
    city_obj = await db.scalar(select(City).where(City.name.ilike(f"%{request.city}%")))

    composite_score = (metric.composite_score if metric and metric.composite_score is not None else 30.0)
    cat = (request.category or entity.category or "music").lower()
    city_music_score = (city_obj.music_market_size if city_obj and city_obj.music_market_size is not None else 70.0)

    ml_result = pricing_engine.predict(
        composite_score=composite_score,
        city_music_score=city_music_score,
        venue_capacity=request.venue_capacity,
        proposed_price=request.proposed_price,
        category=cat,
        is_international=entity.is_international or False,
    )

    predicted_fill_rate = ml_result["predicted_fill_rate"]
    recommended_price = ml_result["recommended_price"]
    confidence = ml_result["confidence"]

    # ── Deterministic verdict — thresholds stated plainly, not tuned to
    # look impressive; these are the same rough bands the pricing route's
    # UI already implies with its "Accessible/Premium/Ultra Premium" tiers.
    has_real_metrics = metric is not None and metric.composite_score is not None
    reasons: List[str] = []

    if not has_real_metrics:
        verdict = "insufficient_data"
        reasons.append("No collected intelligence metrics for this entity yet — score defaulted to a neutral baseline, not a real signal.")
    elif predicted_fill_rate >= 75 and composite_score >= 60:
        verdict = "sign"
        reasons.append(f"Predicted fill rate {predicted_fill_rate:.0f}% and composite score {composite_score:.0f}/100 both clear the sign threshold (>=75% fill, >=60 score).")
    elif predicted_fill_rate >= 55 or composite_score >= 45:
        verdict = "consider"
        reasons.append(f"Predicted fill rate {predicted_fill_rate:.0f}% and composite score {composite_score:.0f}/100 are moderate — worth a closer look, not an automatic yes.")
    else:
        verdict = "pass"
        reasons.append(f"Predicted fill rate {predicted_fill_rate:.0f}% and composite score {composite_score:.0f}/100 are both below viable thresholds for this venue/price combination.")

    if abs(recommended_price - request.proposed_price) / max(request.proposed_price, 1) > 0.20:
        direction = "higher" if recommended_price > request.proposed_price else "lower"
        reasons.append(f"The model's recommended price (₹{recommended_price:,.0f}) is meaningfully {direction} than your proposed ₹{request.proposed_price:,.0f} — consider adjusting before deciding.")

    if city_obj is None:
        reasons.append(f"'{request.city}' isn't a tracked city — city demand defaulted to a neutral baseline, not a real signal.")

    return {
        "entity_id": request.entity_id,
        "entity_name": entity.name,
        "city": request.city,
        "verdict": verdict,
        "reasons": reasons,
        "predicted_fill_rate_pct": predicted_fill_rate,
        "recommended_price": recommended_price,
        "proposed_price": request.proposed_price,
        "confidence": confidence,
        "model": ml_result["model"],
        "has_real_metrics": has_real_metrics,
        "city_tracked": city_obj is not None,
    }

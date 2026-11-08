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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, run_queries
from app.core.sql import ilike_contains
from app.services.latest_metric import latest_metric, trend_direction
from app.services.market_scope import Market, market_clause
from app.models.entity import Entity
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


async def _find_city(db_unused, name: str):
    """Statement helper: exact (case-insensitive) city match preferred, then
    contains-match; deterministic when several cities match (never raises
    MultipleResultsFound, which previously 500'd on e.g. city='a')."""
    exact = func.lower(City.name) == name.lower()
    return (
        select(City)
        .where(ilike_contains(City.name, name))
        .order_by(exact.desc(), City.name)
        .limit(1)
    )


class SignRequest(BaseModel):
    entity_id: str = Field(..., max_length=64, description="UUID of the entity to evaluate")
    city: str = Field(..., min_length=1, max_length=100, description="Target city for the booking")
    venue_capacity: int = Field(..., ge=100, le=100000)
    proposed_price: float = Field(..., ge=100, le=50000, description="Proposed base ticket price (INR)")
    category: Optional[str] = Field(None, max_length=100, description="Event category override")


@router.get("/entities", summary="Ranked entity recommendations worth booking")
async def recommend_entities(
    category: Optional[str] = Query(None, max_length=100, description="Filter: music, comedy, sports, theatre..."),
    city: Optional[str] = Query(None, max_length=100, description="Rank by demand fit for this specific city"),
    is_international: Optional[bool] = Query(None),
    market: Market = "all",
    exclude_watchlisted: bool = Query(False, description="Exclude entities already on your watchlist (per-user: never cached)"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Rules filter (real data required; optional category/city/market/
    international/watchlist exclusion) -> rank by composite_score blended with
    the target city's demand-field score for that category (same field
    /entities/{id}/cities uses). Only entities with a real scored metric are
    candidates; the score is the LATEST scored snapshot (latest_metric()), so
    a newer social-only row can't hide a real score.
    """
    lm = latest_metric()
    # Narrow column list (whole Entity rows are wide; pulling them over the WAN dominated latency).
    stmt = (
        select(Entity.id.label("eid"), Entity.name.label("ename"), Entity.entity_type.label("etype"),
               Entity.category.label("ecat"), Entity.is_international.label("eintl"),
               lm.composite_score, lm.trend_velocity, lm.time, lm.data_completeness)
        .join(lm, Entity.id == lm.entity_id)
        .where(market_clause(market))
    )
    if category:
        stmt = stmt.where(ilike_contains(Entity.category, category))
    if is_international is not None:
        stmt = stmt.where(Entity.is_international == is_international)
    if exclude_watchlisted:
        stmt = stmt.where(Entity.id.notin_(select(Watchlist.entity_id).where(Watchlist.user_id == user.id)))

    if city:
        rows, city_rows = await run_queries(stmt, await _find_city(None, city))
        if not city_rows:
            raise HTTPException(404, f"City '{city}' not tracked")
        city_obj = city_rows[0][0]
    else:
        (rows,) = await run_queries(stmt)
        city_obj = None

    candidates = []
    for metric in rows:
        composite = float(metric.composite_score)
        city_demand = _city_demand_score(city_obj, metric.ecat) if city_obj else None

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
            "entity_id": str(metric.eid),
            "entity_name": metric.ename,
            "entity_type": metric.etype,
            "category": metric.ecat,
            "is_international": metric.eintl or False,
            "composite_score": round(composite, 1),
            "city_demand_score": round(city_demand, 1) if city_demand is not None else None,
            "recommendation_score": round(blended, 1),
            "trend_direction": trend_direction(metric.trend_velocity),
            "data_completeness": metric.data_completeness,
            "last_updated": metric.time.isoformat() if metric.time else None,
        })

    candidates.sort(key=lambda c: (-c["recommendation_score"], c["entity_name"], c["entity_id"]))
    ranked = candidates[:limit]
    for i, c in enumerate(ranked):
        c["rank"] = i + 1

    return {
        "recommendations": ranked,
        "total_candidates": len(candidates),
        "filters_applied": {
            "category": category, "city": city,
            "is_international": is_international, "market": market,
            "exclude_watchlisted": exclude_watchlisted,
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

    lm = latest_metric()
    entity_rows, metric_rows, city_rows = await run_queries(
        select(Entity).where(Entity.id == uid),
        select(lm).where(lm.entity_id == uid),
        await _find_city(None, request.city),
    )
    if not entity_rows:
        raise HTTPException(404, f"Entity '{request.entity_id}' not found")
    entity = entity_rows[0][0]
    metric = metric_rows[0][0] if metric_rows else None
    city_obj = city_rows[0][0] if city_rows else None

    composite_score = (metric.composite_score if metric and metric.composite_score is not None else 30.0)
    cat = (request.category or entity.category or "music").lower()
    city_music_score = (city_obj.music_market_size if city_obj and city_obj.music_market_size is not None else 70.0)

    try:
        ml_result = pricing_engine.predict(
            composite_score=composite_score,
            city_music_score=city_music_score,
            venue_capacity=request.venue_capacity,
            proposed_price=request.proposed_price,
            category=cat,
            is_international=entity.is_international or False,
        )
    except Exception as exc:  # model failure must be a clean 503, not a 500
        logger.error("pricing engine failed in /recommend/sign", error=type(exc).__name__)
        raise HTTPException(503, "Pricing engine failed — cannot produce a sign recommendation")

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

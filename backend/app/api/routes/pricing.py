"""
LiveIQ — Pricing Intelligence Routes (Sprint 3D)
Signal-based ticket pricing recommendations using entity intelligence + city demand.

Endpoints:
  POST /pricing/optimize            → Get recommended price with reasoning
  GET  /pricing/elasticity/{entity_id}  → Price sensitivity curve across cities
  GET  /pricing/benchmarks          → Market pricing benchmarks by category
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.city import City
from app.models.event import Event
from app.models.venue import Venue
from app.api.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.services.city_lookup import resolve_city, escape_like

# ML engine — loads/trains on first call
try:
    from app.services.ml.pricing_engine import pricing_engine
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    pricing_engine = None  # type: ignore

router = APIRouter()
logger = structlog.get_logger()


# ── Request / Response Schemas ─────────────────────────────────────────────────

class PricingRequest(BaseModel):
    entity_id: str = Field(..., description="UUID of the entity to price")
    city: str = Field(..., description="City where event will be held")
    venue_capacity: int = Field(..., ge=100, le=100000, description="Venue capacity (seats)")
    proposed_price: float = Field(..., ge=100, le=50000, description="Proposed base ticket price (INR)")
    category: Optional[str] = Field(None, description="Event category override")
    event_date_month: Optional[int] = Field(None, ge=1, le=12, description="Event month for seasonality")


# ── Category benchmarks (INR) ──────────────────────────────────────────────────
CATEGORY_BENCHMARKS = {
    "music": {"floor": 500, "sweet_spot": 2500, "premium": 8000, "ultra_premium": 25000},
    "bollywood": {"floor": 1000, "sweet_spot": 3000, "premium": 10000, "ultra_premium": 30000},
    "international": {"floor": 2000, "sweet_spot": 6000, "premium": 15000, "ultra_premium": 50000},
    "comedy": {"floor": 400, "sweet_spot": 1200, "premium": 3000, "ultra_premium": 8000},
    "edm": {"floor": 800, "sweet_spot": 2000, "premium": 6000, "ultra_premium": 20000},
    "sports": {"floor": 300, "sweet_spot": 1500, "premium": 5000, "ultra_premium": 15000},
    "theatre": {"floor": 500, "sweet_spot": 1500, "premium": 4000, "ultra_premium": 10000},
    "k-pop": {"floor": 2000, "sweet_spot": 5000, "premium": 12000, "ultra_premium": 35000},
}

CITY_PRICE_MULTIPLIERS = {
    "mumbai": 1.20,
    "delhi ncr": 1.15,
    "bengaluru": 1.18,
    "hyderabad": 1.05,
    "pune": 1.00,
    "chennai": 0.95,
    "kolkata": 0.88,
    "ahmedabad": 0.90,
    "jaipur": 0.82,
    "chandigarh": 0.85,
    "kochi": 0.80,
    "indore": 0.78,
}


TIER_PRICE_MULTIPLIERS = {1: 1.10, 2: 0.95, 3: 0.82}


def _city_multiplier(city_key: str, tier: Optional[int]) -> float:
    """Curated multiplier where we have one, else a tier-based default (not a flat 0.90)."""
    if city_key in CITY_PRICE_MULTIPLIERS:
        return CITY_PRICE_MULTIPLIERS[city_key]
    return TIER_PRICE_MULTIPLIERS.get(tier or 0, 0.80 if tier else 0.90)


@router.post("/optimize", summary="AI-powered ticket pricing recommendation")
async def optimize_pricing(
    request: PricingRequest,
    db: AsyncSession = Depends(get_db),
    # Per ARCHITECTURE_AND_APP_STRUCTURE.md §9: pricing recommendations
    # are part of the Revenue Simulator / Pricing Optimizer — Booker +
    # Analyst + Executive territory, not Marketing/Viewer.
    user: User = Depends(require_roles(UserRole.EXECUTIVE, UserRole.ANALYST, UserRole.BOOKER)),
):
    """
    Returns a data-backed pricing recommendation using:
    - Entity composite score (demand signal)
    - City demand multiplier
    - Venue capacity (supply signal)
    - Category market benchmarks
    - Seasonal demand factor
    """
    # Fetch entity
    try:
        uid = UUID(request.entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity_result = await db.execute(select(Entity).where(Entity.id == uid))
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, f"Entity '{request.entity_id}' not found")

    # Fetch latest metric
    metric_result = await db.execute(
        select(EntityMetric)
        .where(EntityMetric.entity_id == uid, EntityMetric.composite_score.isnot(None))   # newest SCORED row (social-only rows have no score)
        .order_by(desc(EntityMetric.time))
        .limit(1)
    )
    metric = metric_result.scalar_one_or_none()

    # Fetch city
    city_obj = await resolve_city(db, request.city)
    # Canonical name for all downstream city filters (exact match, no LIKE wildcards).
    city_name = city_obj.name if city_obj else request.city.strip()

    # ── Scoring inputs ─────────────────────────────────────────────────────────
    composite_score = (metric.composite_score or 30.0) if metric else 30.0  # default to median
    google_trend = (metric.google_trend_score or 50.0) if metric else 50.0
    news_signal = min((metric.news_mentions_7d or 0) / 20.0, 1.0) if metric else 0.0  # 0-1

    city_key = city_name.lower()
    city_multiplier = _city_multiplier(city_key, city_obj.tier if city_obj else None)
    city_income = (city_obj.avg_monthly_income or 45000) if city_obj else 45000
    income_multiplier = city_income / 50000  # normalized to ₹50k baseline

    # ── Composite demand score ─────────────────────────────────────────────────
    # Normalized 0-1: composite_score/100, google_trend/100, news_signal
    demand_score = (
        (composite_score / 100) * 0.50 +
        (google_trend / 100) * 0.30 +
        news_signal * 0.20
    )

    # ── Capacity factor: larger venue = lower per-ticket value (scarcity premium) ──
    # Small (<1000) → 1.15, Medium (1k-5k) → 1.0, Large (>5k) → 0.90
    if request.venue_capacity < 1000:
        capacity_factor = 1.15
    elif request.venue_capacity < 5000:
        capacity_factor = 1.00
    elif request.venue_capacity < 15000:
        capacity_factor = 0.92
    else:
        capacity_factor = 0.85

    # ── Seasonality factor ─────────────────────────────────────────────────────
    season_factor = 1.0
    if request.event_date_month and city_obj:
        festival_data = city_obj.festival_months or {}
        high_demand = festival_data.get("high_demand", [])
        low_demand = festival_data.get("low_demand", [])
        if request.event_date_month in high_demand:
            season_factor = 1.12
        elif request.event_date_month in low_demand:
            season_factor = 0.88

    # ── International premium ──────────────────────────────────────────────────
    intl_factor = 1.30 if entity.is_international else 1.0

    # ── Category benchmark ────────────────────────────────────────────────────
    cat = (request.category or entity.category or "music").lower()
    cat_key = next((k for k in CATEGORY_BENCHMARKS if k in cat), "music")
    benchmarks = CATEGORY_BENCHMARKS[cat_key]

    # ── ML pricing engine ──────────────────────────────────────────────────────
    city_music_score = (city_obj.music_market_size if city_obj and city_obj.music_market_size is not None else 70.0)

    # ── Sprint 6A features: real DB-derived market-saturation signals ──────────
    # days_since_last_event_in_city: how long since ANY tracked event (any
    # source) took place in this city — a real gap since the routes only
    # track past events, not future bookings.
    last_event_result = await db.execute(
        select(func.max(Event.event_date))
        .join(Venue, Event.venue_id == Venue.id)
        .where(Venue.city.ilike(escape_like(city_name), escape="\\"), Event.event_date <= datetime.now(timezone.utc))
    )
    last_event_date = last_event_result.scalar_one_or_none()
    if last_event_date is not None:
        now = datetime.now(timezone.utc)
        if last_event_date.tzinfo is None:
            last_event_date = last_event_date.replace(tzinfo=timezone.utc)
        days_since_last_event = max(0.0, (now - last_event_date).days)
    else:
        days_since_last_event = None  # no data — let the engine use its neutral default

    # competitor_events_same_weekend: no specific event date exists on this
    # request (only an optional month), so this counts tracked events in the
    # same city AND same calendar month as a same-season competition proxy —
    # coarser than a true same-weekend window, but real data, not fabricated.
    competitor_events_same_weekend = None
    if request.event_date_month:
        competitor_count_result = await db.execute(
            select(func.count())
            .select_from(Event)
            .join(Venue, Event.venue_id == Venue.id)
            .where(
                Venue.city.ilike(escape_like(city_name), escape="\\"),
                extract("month", Event.event_date) == request.event_date_month,
            )
        )
        competitor_events_same_weekend = float(competitor_count_result.scalar_one() or 0)

    # phq_avg_rank: real PredictHQ significance signal for tracked events in
    # the same city (month-scoped like competitor_events_same_weekend above,
    # for the same reason — no specific event date on this request).
    phq_avg_rank = None
    if request.event_date_month:
        phq_rank_result = await db.execute(
            select(func.avg(Event.predicthq_rank))
            .select_from(Event)
            .join(Venue, Event.venue_id == Venue.id)
            .where(
                Venue.city.ilike(escape_like(city_name), escape="\\"),
                extract("month", Event.event_date) == request.event_date_month,
                Event.predicthq_rank.isnot(None),
            )
        )
        avg_rank = phq_rank_result.scalar_one_or_none()
        phq_avg_rank = float(avg_rank) if avg_rank is not None else None

    if ML_AVAILABLE and pricing_engine is not None:
        ml_result = pricing_engine.predict(
            composite_score   = composite_score,
            city_music_score  = city_music_score or 70.0,
            venue_capacity    = request.venue_capacity,
            proposed_price    = request.proposed_price,
            category          = cat,
            is_international  = entity.is_international,
            lead_days         = 60,  # default lead time
            days_since_last_event_in_city = days_since_last_event,
            competitor_events_same_weekend = competitor_events_same_weekend,
            phq_avg_rank = phq_avg_rank,
        )
        recommended      = ml_result["recommended_price"]
        fill_rate_pct    = ml_result["predicted_fill_rate"]
        fill_at_recommended = ml_result.get("predicted_fill_rate_at_recommended")
        ml_confidence    = ml_result["confidence"]
        sensitivity_curve= ml_result.get("sensitivity_curve", [])
        model_name       = ml_result["model"]
    else:
        # Rule-based fallback
        demand_premium = 1.0 + (demand_score - 0.5) * 0.80
        recommended = (
            request.proposed_price *
            demand_premium *
            city_multiplier *
            income_multiplier *
            capacity_factor *
            season_factor *
            intl_factor
        )
        recommended = round(recommended, -2)
        recommended = max(benchmarks["floor"], min(recommended, benchmarks["ultra_premium"]))
        fill_rate_pct  = round(min(95, composite_score * 0.9), 1)
        fill_at_recommended = None
        ml_confidence  = 50
        sensitivity_curve = []
        model_name = "rule_based"

    # Clamp to category benchmarks
    recommended = max(benchmarks["floor"], min(recommended, benchmarks["ultra_premium"]))

    # ── Price tier classification ──────────────────────────────────────────────
    if recommended <= benchmarks["sweet_spot"]:
        price_tier = "Accessible"
    elif recommended <= benchmarks["premium"]:
        price_tier = "Premium"
    else:
        price_tier = "Ultra Premium"

    # ── Confidence score ───────────────────────────────────────────────────────
    has_metric = metric is not None
    if model_name == "ml_gbr":
        confidence = f"High (ML GBR · {ml_confidence:.0f}%)"
    elif has_metric and composite_score > 20:
        confidence = "Medium (rule-based)"
    else:
        confidence = "Low (no live metrics)"

    # ── AI reasoning ───────────────────────────────────────────────────────────
    factors = []
    if composite_score > 50:
        factors.append(f"{entity.name} has a strong composite signal score ({composite_score:.0f}/100)")
    if google_trend > 60:
        factors.append(f"High search demand (Google Trend: {google_trend:.0f}/100)")
    if entity.is_international:
        factors.append("International act commands premium pricing (+30%)")
    if city_multiplier > 1.0:
        factors.append(f"{city_name} is a premium market (+{int((city_multiplier-1)*100)}%)")
    if season_factor > 1.0:
        factors.append("Peak season month — higher demand expected")
    elif season_factor < 1.0:
        factors.append("Low season — consider discounting to drive attendance")
    if request.venue_capacity < 1000:
        factors.append("Intimate venue creates scarcity premium (+15%)")

    reasoning = ". ".join(factors) if factors else "Standard pricing based on category benchmarks."

    return {
        "entity": {
            "id": request.entity_id,
            "name": entity.name,
            "type": entity.entity_type,
            "category": entity.category,
            "is_international": entity.is_international,
        },
        "recommendation": {
            "proposed_price":      request.proposed_price,
            "recommended_price":   recommended,
            "price_tier":          price_tier,
            "confidence":          confidence,
            "reasoning":           reasoning,
            "predicted_fill_rate": fill_rate_pct,
            "predicted_fill_rate_at_recommended": fill_at_recommended,
            "sensitivity_curve":   sensitivity_curve,
        },
        "signals": {
            "composite_score":     round(composite_score, 1),
            "google_trend_score":  round(google_trend, 1),
            "demand_score":        round(demand_score * 100, 1),
            "city_multiplier":     city_multiplier,
            "capacity_factor":     capacity_factor,
            "season_factor":       season_factor,
            "international_factor":intl_factor,
        },
        "benchmarks": {
            "category": cat_key,
            **benchmarks,
        },
        "model": model_name,
    }


@router.get("/elasticity/{entity_id}", summary="Price sensitivity curve across cities")
async def get_price_elasticity(
    entity_id: str,
    proposed_price: float = Query(2000, ge=100, le=50000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns price-to-demand sensitivity across all tracked cities.
    Higher income + stronger market = higher optimal price point.
    """
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity_result = await db.execute(select(Entity).where(Entity.id == uid))
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    metric_result = await db.execute(
        select(EntityMetric).where(EntityMetric.entity_id == uid, EntityMetric.composite_score.isnot(None))
        .order_by(desc(EntityMetric.time)).limit(1)
    )
    metric = metric_result.scalar_one_or_none()
    composite = (metric.composite_score or 30.0) if metric else 30.0

    cities_result = await db.execute(select(City).order_by(City.tier.asc()))
    cities = cities_result.scalars().all()

    curve = []
    for c in cities:
        city_key = c.name.lower()
        city_mult = _city_multiplier(city_key, c.tier)
        income_mult = (c.avg_monthly_income or 45000) / 50000
        demand_mult = 1.0 + (composite / 100 - 0.5) * 0.8
        intl_factor = 1.30 if entity.is_international else 1.0

        optimal = round(proposed_price * demand_mult * city_mult * income_mult * intl_factor, -2)

        curve.append({
            "city": c.name,
            "tier": c.tier,
            "state": c.state,
            "optimal_price": optimal,
            "city_multiplier": city_mult,
            "demand_index": round(demand_mult * 100, 1),
            "affordability_index": round(income_mult * 100, 1),
        })

    curve.sort(key=lambda x: x["optimal_price"], reverse=True)

    return {
        "entity_id": entity_id,
        "entity_name": entity.name,
        "proposed_price": proposed_price,
        "composite_score": composite,
        "elasticity_curve": curve,
        "insight": f"Price range across cities: ₹{min(c['optimal_price'] for c in curve):,.0f} – ₹{max(c['optimal_price'] for c in curve):,.0f}",
    }


@router.get("/benchmarks", summary="Market pricing benchmarks by category")
async def get_pricing_benchmarks(user: User = Depends(get_current_user)):
    """Returns industry pricing benchmarks for each event category (INR)."""
    return {
        "benchmarks": CATEGORY_BENCHMARKS,
        "city_multipliers": CITY_PRICE_MULTIPLIERS,
        "notes": {
            "floor": "Minimum viable ticket price for this category",
            "sweet_spot": "Optimal mass-market price for maximum attendance",
            "premium": "Premium tier — smaller but high-value audience",
            "ultra_premium": "VIP/front-row — small allocation, maximum revenue",
        },
        "currency": "INR",
        "sprint4_note": "Will be calibrated against historical BookMyShow/District pricing data.",
    }

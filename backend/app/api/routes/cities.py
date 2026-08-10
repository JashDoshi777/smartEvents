"""
LiveIQ — City Intelligence Routes (Sprint 3A)
Real PostgreSQL-backed implementation replacing all stubs.

Endpoints:
  GET  /cities/              → List all tracked cities
  GET  /cities/top           → Cities ranked by market composite score
  GET  /cities/gaps          → Market gap detection (high demand, few events)
  GET  /cities/{city}/intelligence  → Full city intelligence card
  GET  /cities/{city}/venues        → Top venues via Ticketmaster
"""

from typing import Optional, List, Dict
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.city import City
from app.models.venue import Venue
from app.models.restaurant import Restaurant
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _city_to_dict(c: City) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "state": c.state,
        "country": c.country or "India",
        "tier": c.tier,
        "population": c.population,
        "metro_population": c.metro_population,
        "avg_monthly_income": c.avg_monthly_income,
        "youth_population_pct": c.youth_population_pct,
        "lat": c.lat,
        "lng": c.lng,
        "top_categories": c.top_categories or [],
        "active_on_district": c.active_on_district or False,
        "district_events_count": c.district_events_count or 0,
        "festival_months": c.festival_months or {},
        "monsoon_months": c.monsoon_months or [],
        "scores": {
            "nightlife": c.nightlife_score,
            "sports_affinity": c.sports_affinity_score,
            "arts_culture": c.arts_culture_score,
            "comedy_market": c.comedy_market_size,
            "music_market": c.music_market_size,
            "composite": _composite(c),
        },
    }


def _composite(c: City) -> Optional[float]:
    """Composite market score — average of all market dimensions."""
    scores = [
        c.nightlife_score,
        c.sports_affinity_score,
        c.arts_culture_score,
        c.comedy_market_size,
        c.music_market_size,
    ]
    valid = [s for s in scores if s is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 1)


# ── Routes — static paths BEFORE dynamic /{city_name} ─────────────────────────

@router.get("/", summary="List all tracked Indian cities")
async def list_cities(
    tier: Optional[int] = Query(None, ge=1, le=4, description="Filter by city tier (1=metro, 4=small)"),
    active_on_district: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns all tracked cities with tier, market scores, and seasonality."""
    stmt = select(City)
    if tier is not None:
        stmt = stmt.where(City.tier == tier)
    if active_on_district is not None:
        stmt = stmt.where(City.active_on_district == active_on_district)

    stmt = stmt.order_by(asc(City.tier), asc(City.name))
    result = await db.execute(stmt)
    cities = result.scalars().all()

    return {
        "cities": [_city_to_dict(c) for c in cities],
        "total": len(cities),
        "tiers": {
            "1": "Metro (Mumbai, Delhi, Bengaluru, Hyderabad)",
            "2": "Major (Pune, Chennai, Kolkata, Ahmedabad)",
            "3": "Emerging (Jaipur, Chandigarh, Kochi, Indore)",
            "4": "Small (not yet tracked)",
        },
    }


@router.get("/top", summary="Top cities ranked by composite market score")
async def get_top_cities(
    limit: int = Query(10, le=50),
    category: Optional[str] = Query(None, description="Filter by top category: music, comedy, sports..."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns cities ranked by composite market score (avg of all market dimensions)."""
    stmt = select(City)
    if category:
        stmt = stmt.where(City.top_categories.contains([category]))
    result = await db.execute(stmt)
    cities = result.scalars().all()

    # Sort by composite score in Python (avoids complex SQL for computed field)
    ranked = sorted(
        [_city_to_dict(c) for c in cities],
        key=lambda x: x["scores"]["composite"] or 0,
        reverse=True,
    )[:limit]

    for i, c in enumerate(ranked):
        c["rank"] = i + 1

    return {
        "cities": ranked,
        "total": len(ranked),
        "ranked_by": "composite_market_score",
        "note": "Composite = avg(nightlife, sports, arts, comedy, music) market scores",
    }


@router.get("/gaps", summary="Market gap detection — high demand, low event supply")
async def get_market_gaps(
    category: Optional[str] = Query(None, description="Filter by: music, comedy, sports..."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Identifies cities where District has no presence but market scores are high.
    These are expansion opportunities — high demand, low supply.
    Sprint 4: will cross-reference Google Trends search volume vs actual event count.
    """
    stmt = select(City).where(City.active_on_district == False)  # noqa: E712 (SQLAlchemy ORM syntax)
    if category:
        stmt = stmt.where(City.top_categories.contains([category]))
    result = await db.execute(stmt)
    cities = result.scalars().all()

    gaps = []
    for c in cities:
        comp = _composite(c)
        if comp and comp >= 65:  # Only high-potential cities
            gaps.append({
                "city": c.name,
                "state": c.state,
                "tier": c.tier,
                "composite_market_score": comp,
                "top_categories": c.top_categories or [],
                "population": c.metro_population or c.population,
                "avg_monthly_income": c.avg_monthly_income,
                "opportunity_score": round(comp * ((c.metro_population or c.population or 1_000_000) / 10_000_000) * 10, 1),
                "reason": f"Tier {c.tier} city with {comp:.0f}/100 market score — District not yet active",
            })

    gaps.sort(key=lambda x: x["opportunity_score"], reverse=True)
    for i, g in enumerate(gaps):
        g["rank"] = i + 1

    return {
        "gaps": gaps,
        "total": len(gaps),
        "methodology": "Cities where active_on_district=False and composite market score >= 65",
        "sprint4_note": "Will add Google Trends demand vs Ticketmaster supply cross-reference.",
    }


@router.get("/{city_name}/intelligence", summary="Full city intelligence report")
async def get_city_intelligence(
    city_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns a full city intelligence card:
    - Demographics, tier, market scores
    - Seasonality: peak months, festival calendar, monsoon risk
    - District presence vs competitor comparison
    - Platform expansion recommendation
    """
    result = await db.execute(
        select(City).where(func.lower(City.name) == city_name.lower().replace("-", " "))
    )
    city = result.scalar_one_or_none()

    if not city:
        # Fuzzy fallback — partial match
        result = await db.execute(
            select(City).where(City.name.ilike(f"%{city_name}%"))
        )
        city = result.scalar_one_or_none()
        if not city:
            raise HTTPException(404, f"City '{city_name}' not found. Use /cities/ to list available cities.")

    data = _city_to_dict(city)
    comp = data["scores"]["composite"]

    # Expansion recommendation
    if not city.active_on_district:
        if comp and comp >= 75:
            recommendation = "HIGH PRIORITY — Strong market scores. Immediate expansion recommended."
        elif comp and comp >= 60:
            recommendation = "MEDIUM PRIORITY — Good market potential. Plan expansion in next quarter."
        else:
            recommendation = "LOW PRIORITY — Emerging market. Monitor for 6 months."
    else:
        recommendation = "ACTIVE — District already operating in this city."

    # Peak season analysis
    festival_data = city.festival_months or {}
    high_demand = festival_data.get("high_demand", [])
    month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    peak_months = [month_names.get(m, str(m)) for m in high_demand]

    # Restaurant/venue partnership candidates — real listings from
    # restaurant_sync.py (Foursquare + OpenStreetMap), not fabricated.
    # No rating field is populated by either source at the free tier, so
    # none is invented here — the frontend must not display a rating for
    # these rows. Sampled evenly across venue types (a plain
    # ORDER BY name LIMIT 10 would be dominated by "restaurant" rows,
    # since that category vastly outnumbers cafes/bars/nightclubs at
    # most tracked cities — cafes and clubs would rarely appear at all).
    restaurants: List[Restaurant] = []
    counts_by_type: Dict[str, int] = {}
    for vt in ("restaurant", "cafe", "bar", "nightclub"):
        count_result = await db.execute(
            select(func.count()).select_from(Restaurant)
            .where(Restaurant.city.ilike(f"%{city.name}%"), Restaurant.venue_type == vt)
        )
        counts_by_type[vt] = count_result.scalar_one() or 0

        type_result = await db.execute(
            select(Restaurant)
            .where(Restaurant.city.ilike(f"%{city.name}%"), Restaurant.venue_type == vt)
            .order_by(Restaurant.name.asc())
            .limit(3)
        )
        restaurants.extend(type_result.scalars().all())

    return {
        **data,
        "intelligence": {
            "expansion_recommendation": recommendation,
            "peak_season_months": peak_months,
            "monsoon_risk": f"Outdoor events risky in months: {[month_names.get(m) for m in (city.monsoon_months or [])]}",
            "income_tier": "Premium" if (city.avg_monthly_income or 0) > 55000 else "Mid-market" if (city.avg_monthly_income or 0) > 40000 else "Value",
            "youth_index": "High" if (city.youth_population_pct or 0) > 40 else "Medium" if (city.youth_population_pct or 0) > 35 else "Low",
            "restaurant_partnerships": [
                {
                    "name": r.name,
                    "venue_type": r.venue_type,
                    "cuisine": ", ".join(sorted(set((r.osm_cuisines or []) + (r.foursquare_categories or [])))[:2]) or None,
                    "rating": None,  # never fabricated — see comment above
                }
                for r in restaurants
            ],
            "venue_counts_by_type": counts_by_type,
        },
    }


@router.get("/{city_name}/venues", summary="Top venues in a city")
async def get_city_venues(
    city_name: str,
    category: Optional[str] = Query(None, description="Filter: music, sports, comedy..."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns venues in the city from the venues table (seeded + ingested data).
    Falls back to a live Ticketmaster lookup only if Postgres has nothing yet.
    """
    stmt = select(Venue).where(Venue.city.ilike(city_name.replace("-", " ")))
    if category:
        stmt = stmt.where(Venue.suitable_categories.contains([category]))
    stmt = stmt.order_by(Venue.total_capacity.desc().nullslast())

    result = await db.execute(stmt)
    db_venues = result.scalars().all()

    if db_venues:
        venues = [
            {
                "id": str(v.id),
                "name": v.name,
                "capacity": v.total_capacity,
                "type": v.venue_type,
                "categories": v.suitable_categories or [],
                "avg_fill_rate": v.avg_fill_rate,
                "avg_ticket_price": v.avg_ticket_price,
                "rating": v.avg_rating,
            }
            for v in db_venues
        ]
        source = "database"
    else:
        venues = []
        try:
            from app.services.ingestion.ticketmaster_client import TicketmasterClient
            async with TicketmasterClient() as client:
                result_tm = await client.search_events(keyword=city_name, size=5)
            # Same shape as the database branch so callers never have to
            # special-case a stripped-down response — fields Ticketmaster
            # doesn't give us are explicit None, not simply absent.
            venues = [
                {
                    "id": None,
                    "name": e.get("venue", city_name + " Venue"),
                    "capacity": None,
                    "type": None,
                    "categories": [],
                    "avg_fill_rate": None,
                    "avg_ticket_price": None,
                    "rating": None,
                }
                for e in result_tm.get("events", [])
            ]
        except Exception as e:
            logger.warning("Ticketmaster venue fetch failed", city=city_name, error=str(e))
        source = "ticketmaster" if venues else "none"

    return {
        "city": city_name,
        "venues": venues,
        "total": len(venues),
        "source": source,
    }


@router.get("/{city_name}/restaurants", summary="Real dining & nightlife venue listings for a city (Foursquare + OpenStreetMap)")
async def get_city_restaurants(
    city_name: str,
    cuisine: Optional[str] = Query(None, description="Filter by cuisine/category substring, e.g. 'indian', 'chinese'"),
    venue_type: Optional[str] = Query(None, description="Filter by venue type: restaurant, cafe, bar, nightclub"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Real venue data from restaurant_sync.py (Foursquare Places API +
    OpenStreetMap/Overpass, daily sync) — restaurants, cafes, bars, and
    nightclubs, each with a real lat/lng from its source (never a
    city-center fallback). No numeric rating is returned — neither
    source provides a real free-tier rating, and this project never
    fabricates one.
    """
    # Cuisine filtering across two differently-shaped array columns
    # (osm_cuisines/foursquare_categories) isn't cleanly expressible as a
    # single SQL ILIKE-over-array condition, so it's applied in Python
    # below — fine at current restaurant volumes (hundreds per city, not
    # millions). When filtering, fetch a larger pool before the Python
    # filter narrows it back down to `limit`.
    stmt = select(Restaurant).where(Restaurant.city.ilike(city_name.replace("-", " ")))
    if venue_type:
        stmt = stmt.where(Restaurant.venue_type == venue_type)
    stmt = stmt.order_by(Restaurant.name.asc()).limit(limit if not cuisine else 2000)

    result = await db.execute(stmt)
    restaurants = result.scalars().all()

    if cuisine:
        cuisine_lower = cuisine.lower()
        restaurants = [
            r for r in restaurants
            if any(cuisine_lower in c.lower() for c in (r.osm_cuisines or []))
            or any(cuisine_lower in c.lower() for c in (r.foursquare_categories or []))
        ][:limit]

    return {
        "city": city_name,
        "restaurants": [
            {
                "id": str(r.id),
                "name": r.name,
                "venue_type": r.venue_type,
                "cuisines": sorted(set((r.osm_cuisines or []) + (r.foursquare_categories or []))),
                "address": r.formatted_address,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "phone": r.phone,
                "website": r.website,
                "opening_hours": r.opening_hours,
                "sources": [
                    s for s, present in [("foursquare", r.foursquare_place_id is not None), ("openstreetmap", r.osm_id is not None)]
                    if present
                ],
            }
            for r in restaurants
        ],
        "total": len(restaurants),
        "source": "foursquare+openstreetmap",
        "data_note": "Real dining & nightlife venue listings (restaurants, cafes, bars, nightclubs), cross-validated where both sources agree on the same place. No rating shown — neither source provides a real, free-tier rating for this data.",
    }

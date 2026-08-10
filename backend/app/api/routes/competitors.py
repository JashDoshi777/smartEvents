"""
LiveIQ — Competitor Intelligence Routes (Sprint 3B)
Real data from Ticketmaster + NewsAPI to profile competitor activity.

Competitors tracked: BookMyShow (BMS), Insider (Paytm), Ticketmaster India
Strategy: Ticketmaster shared inventory + NewsAPI press coverage

Endpoints:
  GET /competitors/intelligence      → Platform comparison by city
  GET /competitors/gaps              → Expansion opportunities
  GET /competitors/activity-feed     → Recent competitor news
"""

import asyncio
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.city import City
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()


# Competitor platform metadata
PLATFORMS = {
    "district": {
        "name": "District by Zomato",
        "parent": "Zomato",
        "founded": 2022,
        "strengths": ["Restaurant + event cross-sell", "Zomato user base", "Premium positioning"],
        "markets": ["Mumbai", "Delhi NCR", "Bengaluru", "Hyderabad", "Pune"],
    },
    "bookmyshow": {
        "name": "BookMyShow",
        "parent": "Bigtree Entertainment",
        "founded": 1999,
        "strengths": ["Market leader", "Massive inventory", "Movie + live events"],
        "markets": ["All India", "International"],
    },
    "insider": {
        "name": "Insider.in",
        "parent": "Paytm",
        "founded": 2015,
        "strengths": ["Paytm payments integration", "Independent/underground music", "College circuit"],
        "markets": ["Mumbai", "Delhi NCR", "Bengaluru", "Pune", "Hyderabad", "Chennai"],
    },
    "ticketmaster_india": {
        "name": "Ticketmaster India",
        "parent": "Live Nation",
        "founded": 2018,
        "strengths": ["International acts", "Live Nation roster", "Premium venues"],
        "markets": ["Mumbai", "Delhi NCR", "Bengaluru"],
    },
}


@router.get("/intelligence", summary="Competitor platform intelligence by city")
async def get_competitor_intelligence(
    city: str = Query("Mumbai", description="City to analyze"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns competitor activity analysis for a given city.
    Data: Ticketmaster live events + NewsAPI coverage.
    """
    # Fetch live event count for city from Ticketmaster
    ticketmaster_events = []
    news_mentions = {}

    try:
        from app.services.ingestion.ticketmaster_client import TicketmasterClient
        async with TicketmasterClient() as client:
            result = await client.search_events(keyword=city, country_code="IN", size=50)
        ticketmaster_events = result.get("events", [])
        logger.info("Ticketmaster events fetched", city=city, count=len(ticketmaster_events))
    except Exception as e:
        logger.warning("Ticketmaster fetch failed", city=city, error=str(e))

    # Get news mentions for each competitor
    try:
        from app.services.ingestion.newsapi_client import NewsAPIClient
        async with NewsAPIClient() as client:
            tasks = {
                "bookmyshow": client.search_news(f"BookMyShow {city}", page_size=5),
                "insider": client.search_news(f"Insider.in {city}", page_size=5),
                "district": client.search_news(f"District Zomato {city}", page_size=5),
            }
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for key, result in zip(tasks.keys(), results):
                if isinstance(result, dict):
                    news_mentions[key] = result.get("total_results", 0)
                else:
                    news_mentions[key] = 0
    except Exception as e:
        logger.warning("NewsAPI fetch failed", error=str(e))
        news_mentions = {"bookmyshow": 0, "insider": 0, "district": 0}

    # City presence from our DB
    city_result = await db.execute(
        select(City).where(City.name.ilike(f"%{city}%"))
    )
    city_obj = city_result.scalar_one_or_none()
    district_active = city_obj.active_on_district if city_obj else False
    district_events = city_obj.district_events_count if city_obj else 0

    # Build comparison
    platforms_analysis = {
        "district": {
            **PLATFORMS["district"],
            "active_in_city": district_active,
            "estimated_events": district_events,
            "news_mentions_7d": news_mentions.get("district", 0),
            "market_position": "Growing" if district_active else "Not active",
        },
        "bookmyshow": {
            **PLATFORMS["bookmyshow"],
            "active_in_city": city in PLATFORMS["bookmyshow"]["markets"] or "All India" in PLATFORMS["bookmyshow"]["markets"],
            "news_mentions_7d": news_mentions.get("bookmyshow", 0),
            "market_position": "Dominant (no direct event-count API — not measured)",
        },
        "insider": {
            **PLATFORMS["insider"],
            "active_in_city": city in PLATFORMS["insider"]["markets"],
            "news_mentions_7d": news_mentions.get("insider", 0),
            "market_position": "Challenger (no direct event-count API — not measured)",
        },
        "ticketmaster_india": {
            **PLATFORMS["ticketmaster_india"],
            "active_in_city": city in PLATFORMS["ticketmaster_india"]["markets"],
            "live_events_count": len(ticketmaster_events),
            "news_mentions_7d": 0,
            "market_position": "Niche (international acts only)",
        },
    }

    return {
        "city": city,
        "total_ticketmaster_events_live": len(ticketmaster_events),
        "platforms": platforms_analysis,
        "district_opportunity": {
            "city_tier": city_obj.tier if city_obj else "Unknown",
            "district_active": district_active,
            "recommendation": "EXPAND" if not district_active else "GROW",
        },
        "data_sources": ["ticketmaster", "newsapi"],
        "note": "Only Ticketmaster provides a live per-city event count today. BookMyShow/Insider have no public event-count API — their activity is inferred from configured market coverage and NewsAPI mentions, not counted directly.",
    }


@router.get("/gaps", summary="Cities where District can expand vs competitors")
async def get_competitor_gaps(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns cities where BMS/Insider are active but District is not.
    These are the highest-priority expansion targets.
    """
    result = await db.execute(
        select(City).where(City.active_on_district == False).order_by(City.tier.asc())  # noqa: E712
    )
    inactive_cities = result.scalars().all()

    gaps = []
    for c in inactive_cities:
        scores = [c.nightlife_score, c.music_market_size, c.comedy_market_size]
        valid = [s for s in scores if s is not None]
        avg = round(sum(valid) / len(valid), 1) if valid else 0

        insider_active = c.name in PLATFORMS["insider"]["markets"]

        gaps.append({
            "city": c.name,
            "state": c.state,
            "tier": c.tier,
            "population": c.metro_population or c.population,
            "avg_event_market_score": avg,
            "competitor_presence": {
                "bookmyshow": "Active" if c.name in PLATFORMS["bookmyshow"]["markets"] or "All India" in PLATFORMS["bookmyshow"]["markets"] else "Unknown",
                "insider": "Active" if insider_active else "Inactive",
                "district": "Not Active ← OPPORTUNITY",
            },
            "priority": "HIGH" if c.tier <= 2 and avg >= 70 else "MEDIUM" if c.tier <= 3 else "LOW",
        })

    # Sort: HIGH priority first
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    gaps.sort(key=lambda x: (priority_order[x["priority"]], -x["avg_event_market_score"]))

    return {
        "gaps": gaps,
        "total": len(gaps),
        "high_priority": sum(1 for g in gaps if g["priority"] == "HIGH"),
        "insight": "All listed cities have BookMyShow presence. District can differentiate with premium positioning.",
    }


@router.get("/activity-feed", summary="Recent competitor news and announcements")
async def get_competitor_activity(
    limit: int = Query(10, le=30),
    user: User = Depends(get_current_user),
):
    """
    Returns recent news about competitor platforms — tour announcements,
    funding news, new city launches, partnerships.
    """
    articles = []
    queries = [
        ("BookMyShow", "BookMyShow concert event India 2025"),
        ("Insider.in", "Insider.in event India 2025"),
        ("District Zomato", "District Zomato event India 2025"),
        ("Live Nation India", "Live Nation India concert 2025"),
    ]

    try:
        from app.services.ingestion.newsapi_client import NewsAPIClient
        async with NewsAPIClient() as client:
            for platform, query in queries:
                result = await client.search_news(query, page_size=3)
                for article in result.get("articles", []):
                    articles.append({
                        "platform": platform,
                        "title": article.get("title"),
                        "source": article.get("source", {}).get("name"),
                        "published_at": article.get("publishedAt"),
                        "url": article.get("url"),
                    })
    except Exception as e:
        logger.warning("NewsAPI competitor feed failed", error=str(e))

    # Sort by date
    articles.sort(key=lambda x: x.get("published_at") or "", reverse=True)

    return {
        "articles": articles[:limit],
        "total": len(articles),
        "platforms_monitored": [p for p, _ in queries],
        "note": "Live from NewsAPI — refreshed on every request.",
    }

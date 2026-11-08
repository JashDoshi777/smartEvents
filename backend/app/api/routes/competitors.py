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
import time
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.city import City
from app.api.deps import get_current_user
from app.models.user import User
from app.models.venue import Venue
from app.models.event import Event
from app.services.city_lookup import resolve_city, escape_like

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


# ── In-process stale-while-revalidate cache for third-party calls ─────────────
# NewsAPI/Ticketmaster are slow and rate-limited (16-19s with client retries). Responses are
# cached 30 min; once stale they are served instantly while ONE background task refreshes.
# A cold miss waits at most COLD_WAIT seconds, then returns the fallback while the fetch finishes
# in the background — so the UI never waits on a third party.
EXT_TTL = 1800
EXT_STALE_MAX = 6 * 3600
COLD_WAIT = 2.5
_EXT: dict = {}            # key -> (value, fetched_at)
_EXT_TASKS: dict = {}      # key -> asyncio.Task (single-flight)
_EXTERNAL_FALLBACK = {"tm_count": 0, "news": {"bookmyshow": 0, "insider": 0, "district": 0}, "news_available": False}


def _spawn(key, factory):
    task = _EXT_TASKS.get(key)
    if task and not task.done():
        return task

    async def run():
        try:
            val = await factory()
            ts = time.time()
            if isinstance(val, dict) and val.get("news_available") is False:
                ts -= EXT_TTL - 120     # an outage result is retried in ~2 min, not held for 30
            _EXT[key] = (val, ts)
            return val
        finally:
            _EXT_TASKS.pop(key, None)

    task = asyncio.create_task(run())
    _EXT_TASKS[key] = task
    task.add_done_callback(_consume_task_error)
    return task


def _consume_task_error(task: "asyncio.Task") -> None:
    """A failed third-party refresh is an expected outage, not a crash: log once, never
    let asyncio emit 'Task exception was never retrieved'."""
    if not task.cancelled() and task.exception() is not None:
        import structlog
        structlog.get_logger().warning("external refresh failed", error=str(task.exception()))


async def _swr(key, factory, fallback):
    hit = _EXT.get(key)
    now = time.time()
    if hit and now - hit[1] < EXT_TTL:
        return hit[0]
    if hit and now - hit[1] < EXT_STALE_MAX:
        _spawn(key, factory)
        return hit[0]
    task = _spawn(key, factory)
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=COLD_WAIT)
    except Exception:
        return fallback


async def _fetch_external(city: str) -> dict:
    tm_count, news, news_available = 0, {"bookmyshow": 0, "insider": 0, "district": 0}, True
    try:
        from app.services.ingestion.ticketmaster_client import TicketmasterClient
        async with TicketmasterClient() as client:
            result = await asyncio.wait_for(client.search_events(keyword=city, country_code="IN", size=50), timeout=7)
        tm_count = len(result.get("events", []))
    except Exception as e:
        logger.warning("Ticketmaster fetch failed", city=city, error=str(e))
    try:
        from app.services.ingestion.newsapi_client import NewsAPIClient
        async with NewsAPIClient() as client:
            tasks = {
                "bookmyshow": client.search_news(f"BookMyShow {city}", page_size=5),
                "insider": client.search_news(f"Insider.in {city}", page_size=5),
                "district": client.search_news(f"District Zomato {city}", page_size=5),
            }
            results = await asyncio.wait_for(asyncio.gather(*tasks.values(), return_exceptions=True), timeout=20)
            for key, result in zip(tasks.keys(), results):
                if isinstance(result, dict):
                    news[key] = result.get("total_results", 0)
                else:
                    news_available = False
    except Exception as e:
        logger.warning("NewsAPI fetch failed", error=str(e))
        news_available = False
    return {"tm_count": tm_count, "news": news, "news_available": news_available}


async def _fetch_feed(queries) -> dict:
    articles, ok = [], True
    try:
        from app.services.ingestion.newsapi_client import NewsAPIClient
        async with NewsAPIClient() as client:
            results = await asyncio.wait_for(asyncio.gather(*(client.search_news(q, page_size=3) for _, q in queries), return_exceptions=True), timeout=25)
        for (platform, _q), result in zip(queries, results):
            if not isinstance(result, dict):
                ok = False
                continue
            for article in result.get("articles", []):
                articles.append({"platform": platform, "title": article.get("title"), "source": article.get("source", {}).get("name"),
                                 "published_at": article.get("publishedAt"), "url": article.get("url")})
    except Exception as e:
        logger.warning("NewsAPI competitor feed failed", error=str(e))
        ok = False
    if not articles and ok is False:
        raise RuntimeError("news unavailable")   # don't cache an outage as if it were an empty feed
    return {"articles": articles, "ok": ok}


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
    ext = await _swr(f"intel:{city.strip().lower()}", lambda: _fetch_external(city.strip()), fallback=_EXTERNAL_FALLBACK)
    ticketmaster_events = [None] * ext["tm_count"]
    news_mentions = ext["news"]
    news_available = ext["news_available"]

    # City presence from our DB
    city_obj = await resolve_city(db, city)
    if city_obj:
        city = city_obj.name   # canonical casing so market-list membership checks work for "mumbai"
    district_active = bool(city_obj.active_on_district) if city_obj else False
    # Real count of District-sourced events at tracked venues in this city; the stored
    # counter is only a fallback when no event is linked to a venue yet.
    real_district_events = await db.scalar(
        select(func.count()).select_from(Event).join(Venue, Event.venue_id == Venue.id)
        .where(Event.source == "district", Venue.city.ilike(escape_like(city), escape="\\"))
    ) or 0
    district_events = max(real_district_events, (city_obj.district_events_count or 0) if city_obj else 0)
    # District's markets come from the cities table, not a hard-coded list that disagreed with it.
    active_names = (await db.execute(select(City.name).where(City.active_on_district == True).order_by(City.name))).scalars().all()  # noqa: E712

    # Build comparison
    platforms_analysis = {
        "district": {
            **PLATFORMS["district"],
            "markets": list(active_names),
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
        "news_available": news_available,
        "data_sources": ["ticketmaster", "newsapi"],
        "note": "Only Ticketmaster provides a live per-city event count today. BookMyShow/Insider have no public event-count API — their activity is inferred from configured market coverage and NewsAPI mentions, not counted directly.",
    }


@router.get("/coverage", summary="Every tracked city: market strength vs District presence")
async def get_coverage(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Per-city market score (avg of nightlife/music/comedy), District presence, rival presence
    (configured market lists) and real event counts by source at tracked venues."""
    cities = (await db.execute(select(City).order_by(City.tier.asc(), City.name.asc()))).scalars().all()
    rows = (await db.execute(
        select(Venue.city, Event.source, func.count())
        .select_from(Event).join(Venue, Event.venue_id == Venue.id)
        .group_by(Venue.city, Event.source)
    )).all()
    by_city: dict = {}
    for vcity, src, n in rows:
        by_city.setdefault((vcity or "").lower(), {})[src or "unknown"] = n
    out = []
    for c in cities:
        scores = [x for x in (c.nightlife_score, c.music_market_size, c.comedy_market_size) if x is not None]
        out.append({
            "city": c.name,
            "state": c.state,
            "tier": c.tier,
            "market_score": round(sum(scores) / len(scores), 1) if scores else None,
            "district_active": bool(c.active_on_district),
            "bookmyshow": "All India" in PLATFORMS["bookmyshow"]["markets"] or c.name in PLATFORMS["bookmyshow"]["markets"],
            "insider": c.name in PLATFORMS["insider"]["markets"],
            "ticketmaster_india": c.name in PLATFORMS["ticketmaster_india"]["markets"],
            "events_by_source": by_city.get(c.name.lower(), {}),
        })
    out.sort(key=lambda r: (-(r["market_score"] or 0), r["city"]))
    return {"cities": out, "total": len(out), "note": "Market score = average of nightlife, music and comedy market scores. Rival presence reflects configured market coverage, not measured inventory."}


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
        select(City).where(City.active_on_district == False).order_by(City.tier.asc().nullslast(), City.name.asc())  # noqa: E712
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
            "scored": bool(valid),
            "competitor_presence": {
                "bookmyshow": "Active" if c.name in PLATFORMS["bookmyshow"]["markets"] or "All India" in PLATFORMS["bookmyshow"]["markets"] else "Unknown",
                "insider": "Active" if insider_active else "Inactive",
                "district": "Not Active ← OPPORTUNITY",
            },
            "priority": "HIGH" if (c.tier or 9) <= 2 and avg >= 70 else "MEDIUM" if (c.tier or 9) <= 3 else "LOW",
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
    news_ok = True
    queries = [
        ("BookMyShow", "BookMyShow concert event India 2025"),
        ("Insider.in", "Insider.in event India 2025"),
        ("District Zomato", "District Zomato event India 2025"),
        ("Live Nation India", "Live Nation India concert 2025"),
    ]

    feed = await _swr("feed", lambda: _fetch_feed(queries), fallback={"articles": [], "ok": False})
    articles = list(feed["articles"])
    news_ok = feed["ok"]

    # Sort by date
    articles.sort(key=lambda x: x.get("published_at") or "", reverse=True)

    return {
        "articles": articles[:limit],
        "total": len(articles),
        "platforms_monitored": [p for p, _ in queries],
        "news_available": news_ok or bool(articles),
        "note": "Live from NewsAPI." if (news_ok or articles) else "The news source is rate-limited or unreachable right now, so no coverage could be fetched. Try again in a few minutes.",
    }

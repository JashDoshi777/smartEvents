"""
LiveIQ — Dashboard Summary Routes

Aggregates all dashboard-needed data into a single API call.

Endpoints:
  GET /dashboard/summary  → Full dashboard payload (entities, cities, events, breakdowns)
  GET /dashboard/alerts   → Live alerts derived from entity metrics + city data

All independent queries run concurrently (app.core.database.run_queries), so a
cold call costs ~1-2 DB round-trips instead of ~12. Scores come from
latest_metric() and the headline numbers from app.services.portfolio, so they
are identical to /executive/kpis and /executive/portfolio.
"""

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db, run_queries
from app.models.city import City
from app.models.entity import Entity
from app.models.event import Event
from app.models.metrics import EntityMetric
from app.models.user import User
from app.models.venue import Venue
from app.services.latest_metric import latest_metric, score_fields
from app.services.market_scope import Market, market_clause
from app.services.portfolio import stats_dict, stats_stmt

router = APIRouter()
logger = structlog.get_logger()


def _f(v, nd=1):
    return round(float(v), nd) if v is not None else None


@router.get("/summary", summary="Full dashboard data payload")
async def get_dashboard_summary(
    market: Market = "all",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Single endpoint that returns everything the dashboard needs."""
    generated_at = datetime.now(timezone.utc)
    lm = latest_metric()
    scope = market_clause(market)

    counts_stmt = select(
        func.count(City.id),
        func.count(City.id).filter(City.active_on_district.is_(True)),
        select(func.count(Event.id)).scalar_subquery(),
    )
    trending_stmt = (
        select(Entity.id, Entity.name, Entity.entity_type, Entity.category, Entity.country,
               Entity.is_international, lm.composite_score, lm.google_trend_score,
               lm.news_mentions_7d, lm.lastfm_listeners, lm.data_completeness, lm.score_confidence, lm.signals_used)
        .join(lm, Entity.id == lm.entity_id)
        .where(scope, lm.composite_score.isnot(None))        # unrated entities are never ranked
        .order_by(desc(lm.composite_score), Entity.name)
        .limit(10)
    )
    cities_stmt = (
        select(City.name, City.tier, City.music_market_size, City.nightlife_score,
               City.active_on_district, City.population)
        .order_by(City.music_market_size.desc().nullslast(), City.name)
        .limit(8)
    )
    now = generated_at
    events_stmt = (
        select(Event.id, Event.title, Venue.city, Venue.name, Event.event_date, Event.category,
               Event.ticket_price_min, Event.ticket_price_max, Event.source)
        .outerjoin(Venue, Event.venue_id == Venue.id)
        .where(Event.event_date.isnot(None))
        # Future events first (soonest first); if fewer than 6 are upcoming the
        # list is topped up with the most recent past events (flagged
        # is_upcoming=false) rather than showing an empty panel when the event
        # feed is stale.
        .order_by(case((Event.event_date >= now, 0), else_=1),
                  func.abs(func.extract("epoch", Event.event_date - now)), Event.id)
        .limit(6)
    )
    cat_stmt = (
        select(Entity.category, func.count(Entity.id).label("count"))
        .where(Entity.category.isnot(None), scope)
        .group_by(Entity.category)
        .order_by(desc("count"), Entity.category)
        .limit(6)
    )
    type_stmt = (
        select(Entity.entity_type, func.count(Entity.id).label("count"))
        .where(scope)
        .group_by(Entity.entity_type)
        .order_by(desc("count"), Entity.entity_type)
    )

    stats_rows, counts_rows, trending_rows, city_rows, event_rows, cat_rows, type_rows = await run_queries(
        stats_stmt(market), counts_stmt, trending_stmt, cities_stmt, events_stmt, cat_stmt, type_stmt
    )
    stats = stats_dict(stats_rows[0])
    total_cities, active_cities, total_events = counts_rows[0]
    total_cities, active_cities = total_cities or 0, active_cities or 0

    return {
        "generated_at": generated_at.isoformat(),
        "market": market,
        "hero": {
            "total_entities": stats["total"],
            "entities_with_metrics": stats["scored"],
            "total_cities": total_cities,
            "active_cities": active_cities,
            "expansion_targets": total_cities - active_cities,
            "total_events": total_events or 0,
            "international_acts": stats["international"],
            "domestic_acts": stats["domestic"],
            "avg_composite_score": stats["avg_score"],
            "unrated_entities": stats["unrated"],
        },
        "trending_entities": [
            {
                "id": str(r[0]), "name": r[1], "type": r[2], "category": r[3], "country": r[4],
                "is_international": r[5] or False,
                **score_fields(r[6], r[11], r[12]),
                "google_trend": r[7], "news_mentions_7d": r[8], "listeners": r[9],
                "data_completeness": r[10],
            }
            for r in trending_rows
        ],
        "city_heat": [
            {"city": r[0], "tier": r[1], "music_score": r[2], "nightlife_score": r[3],
             "active_on_district": r[4] or False}
            for r in city_rows
        ],
        "upcoming_events": [
            {"id": str(r[0]), "name": r[1], "city": r[2], "venue": r[3],
             "event_date": r[4].isoformat() if r[4] else None, "category": r[5],
             "is_upcoming": bool(r[4] and r[4] >= now),
             "min_price": float(r[6]) if r[6] is not None else None,
             "max_price": float(r[7]) if r[7] is not None else None, "source": r[8]}
            for r in event_rows
        ],
        "category_breakdown": [{"category": r[0], "count": r[1]} for r in cat_rows],
        "type_breakdown": [{"type": r[0], "count": r[1]} for r in type_rows],
    }


@router.get("/alerts", summary="Live alerts from entity metrics and city data")
async def get_dashboard_alerts(
    market: Market = "all",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Alert objects derived from:
    - entities whose Google Trend score exceeds their composite (breakout signal)
    - entities with the most news mentions in 7 days (buzz)
    - high-demand cities with no active District presence (gap)
    """
    alerts = []
    now = datetime.now(timezone.utc).isoformat()
    lm = latest_metric()
    scope = market_clause(market)

    news_stmt = (
        select(Entity.name, Entity.category, lm.news_mentions_7d)
        .join(lm, Entity.id == lm.entity_id)
        .where(lm.news_mentions_7d > 0, scope)
        .order_by(desc(lm.news_mentions_7d), Entity.name)
        .limit(2)
    )
    gap_stmt = (
        select(City.name, City.tier, City.music_market_size)
        .where(City.active_on_district.is_not(True), City.music_market_size.isnot(None))
        .order_by(City.music_market_size.desc(), City.name)
        .limit(2)
    )
    news_rows, gap_rows = await run_queries(news_stmt, gap_stmt)

    # "Rising attention" is measured, not inferred: real week-over-baseline Wikipedia pageview change that clears the
    # baseline floor and the |robust z| >= 1.5 test (services/momentum.py). The old alert compared Google's 0-100
    # query-relative number with the composite, which is not a demand signal.
    try:
        from app.services.momentum import momentum_for_market
        mom = await momentum_for_market(db, scope, 2)
    except Exception:  # noqa: BLE001  (table missing on an old DB: no alert rather than a 500)
        mom = {"risers": []}
    for r in mom["risers"]:
        alerts.append({
            "type": "breakout",
            "title": f"{r['name']}: Wikipedia attention rising",
            "message": f"{r['views_7d']:,} Wikipedia views last full week, {r['momentum_pct']:+.0f}% vs the prior 4-week average ({r['views_28d_avg_weekly']:,.0f}/week).",
            "entity": r["name"], "category": r.get("category"), "severity": "high", "ts": now,
        })
    for name, cat, news in news_rows:
        alerts.append({
            "type": "buzz", "title": f"{name} in the news",
            "message": f"{news} news mentions in the last 7 days — consider fast-tracking booking.",
            "entity": name, "category": cat, "severity": "medium", "ts": now,
        })
    for city, tier, score in gap_rows:
        alerts.append({
            "type": "opportunity", "title": f"{city} market gap detected",
            "message": f"Tier-{tier} city with music score {score} — no active District events. Competitor window open.",
            "entity": None, "category": "Market", "severity": "medium", "ts": now,
        })

    if not alerts:
        alerts.append({
            "type": "info", "title": "No alerts yet",
            "message": "Run the entity metrics worker to generate live breakout and buzz alerts.",
            "entity": None, "category": None, "severity": "low", "ts": now,
        })

    return {"alerts": alerts, "total": len(alerts), "market": market, "generated_at": now}


@router.get("/movers", summary="Biggest composite-score movers between the last two snapshots")
async def get_dashboard_movers(
    market: Market = "all",
    limit: int = Query(5, ge=1, le=25),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """delta = newest scored snapshot minus the one before it, per entity (zero deltas excluded)."""
    ranked = (
        select(
            EntityMetric.entity_id.label("entity_id"),
            EntityMetric.composite_score.label("score"),
            EntityMetric.time.label("t"),
            func.row_number().over(partition_by=EntityMetric.entity_id, order_by=EntityMetric.time.desc()).label("rn"),
        )
        .where(EntityMetric.composite_score.isnot(None))
        .subquery("ranked")
    )
    cur, prev = ranked.alias("cur"), ranked.alias("prev")
    delta = cur.c.score - prev.c.score
    base = (
        select(Entity.id, Entity.name, Entity.category, Entity.entity_type,
               cur.c.score, prev.c.score, delta.label("delta"), cur.c.t, prev.c.t)
        .join(cur, cur.c.entity_id == Entity.id)
        .join(prev, prev.c.entity_id == Entity.id)
        .where(cur.c.rn == 1, prev.c.rn == 2, market_clause(market))
    )
    total_compared = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    risers = (await db.execute(base.where(delta >= 0.05).order_by(delta.desc()).limit(limit))).all()
    fallers = (await db.execute(base.where(delta <= -0.05).order_by(delta.asc()).limit(limit))).all()

    def fmt(r):
        return {"id": str(r[0]), "name": r[1], "category": r[2], "type": r[3],
                "score": round(r[4], 1), "previous_score": round(r[5], 1), "delta": round(r[6], 1),
                "as_of": r[7].isoformat() if r[7] else None, "previous_as_of": r[8].isoformat() if r[8] else None}

    return {"risers": [fmt(r) for r in risers], "fallers": [fmt(r) for r in fallers],
            "compared": total_compared, "generated_at": datetime.now(timezone.utc).isoformat()}

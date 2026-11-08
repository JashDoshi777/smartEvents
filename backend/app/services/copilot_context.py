"""Grounding for the AI Copilot: builds a compact, real-data context block from our own DB.

The model previously had only a static prompt, so any "which city / what price" answer was
invented. This pulls (a) every tracked city's real scores, (b) entities mentioned in the
question (or the top-scoring ones) with their latest metrics + booking fees, (c) upcoming
events (filtered by a mentioned city), (d) venue capacity per mentioned city and (e) price
benchmarks when the question is about pricing. It also returns human-readable `sources`
so the UI can show what data an answer was grounded in. Never raises — grounding is
best-effort and a DB hiccup must not take chat down.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.city import City
from app.models.entity import Entity
from app.models.event import Event
from app.models.metrics import EntityMetric
from app.models.venue import Venue

logger = structlog.get_logger()

GROUNDING_RULES = """

GROUNDING RULES (mandatory):
- The "LIVE DATA" block below is queried from LiveIQ's own database just now. Treat it as ground truth.
- When you quote a score, count, price, capacity or date, use the exact figure from LIVE DATA and say which dataset it came from (e.g. "city market scores", "venue capacities").
- If the answer needs data that is not in LIVE DATA, say that plainly and give a clearly-labelled estimate or the signal to check. Never invent figures, events or artists that are not in LIVE DATA.
- Express money in Indian rupees (₹) using lakh/crore (₹1,00,000 = 1 lakh, ₹1,00,00,000 = 1 crore).
- Scores are 0-100. Cities with District "not active" are expansion candidates.
"""


def inr_short(v) -> str:
    if v is None:
        return "n/a"
    v = float(v)
    if v >= 1e7:
        return f"₹{v / 1e7:.2f} crore"
    if v >= 1e5:
        return f"₹{v / 1e5:.2f} lakh"
    return f"₹{v:,.0f}"


def _f(v, nd=0):
    return "n/a" if v is None else (f"{v:.{nd}f}" if nd else f"{v:.0f}")


async def build_context(db: AsyncSession, question: str) -> Tuple[str, List[str]]:
    q = (question or "").lower()
    lines: List[str] = []
    sources: List[str] = []
    try:
        cities = (await db.execute(select(City).order_by(City.tier.asc(), City.name.asc()))).scalars().all()
        mentioned = [c for c in cities if c.name.lower() in q or c.name.lower().split()[0] in q.replace("-", " ").split()]
        if cities:
            lines.append(f"CITY MARKET SCORES ({len(cities)} tracked cities; scores 0-100):")
            for c in cities:
                comp = [x for x in (c.nightlife_score, c.sports_affinity_score, c.arts_culture_score, c.comedy_market_size, c.music_market_size) if x is not None]
                lines.append(
                    f"- {c.name} ({c.state or '—'}, Tier {c.tier}): composite {round(sum(comp)/len(comp),1) if comp else 'n/a'}, "
                    f"nightlife {_f(c.nightlife_score)}, music {_f(c.music_market_size)}, comedy {_f(c.comedy_market_size)}, "
                    f"sports {_f(c.sports_affinity_score)}, arts {_f(c.arts_culture_score)}, avg monthly income {inr_short(c.avg_monthly_income)}, "
                    f"metro population {c.metro_population or c.population or 'n/a'}, District {'ACTIVE' if c.active_on_district else 'not active'}"
                    + (f", peak months {c.festival_months.get('high_demand')}" if (c.festival_months or {}).get('high_demand') else "")
                    + (f", monsoon months {c.monsoon_months}" if c.monsoon_months else "")
                )
            sources.append(f"City market scores ({len(cities)} cities)")

        # Entities: named in the question, else the top by composite score
        latest = (
            select(EntityMetric.entity_id, func.max(EntityMetric.time).label("t"))
            .where(EntityMetric.composite_score.isnot(None)).group_by(EntityMetric.entity_id).subquery()
        )
        base = (
            select(Entity, EntityMetric)
            .join(latest, latest.c.entity_id == Entity.id)
            .join(EntityMetric, (EntityMetric.entity_id == latest.c.entity_id) & (EntityMetric.time == latest.c.t))
            .where(Entity.status == "active")
        )
        rows = (await db.execute(base.order_by(EntityMetric.composite_score.desc().nullslast()).limit(400))).all()
        named = [(e, m) for e, m in rows if len(e.name) > 3 and e.name.lower() in q]
        picked = named[:6]
        top = [r for r in rows if r not in picked][: max(0, 12 - len(picked))]
        if picked or top:
            lines.append("\nARTISTS / ENTITIES (latest metrics; composite 0-100):")
            for e, m in picked + top:
                fee = (f"booking fee {inr_short(e.booking_price_range_min)}–{inr_short(e.booking_price_range_max)}"
                       if e.booking_price_range_min is not None and e.booking_price_range_max is not None else "booking fee n/a")
                lines.append(
                    f"- {e.name} [{e.entity_type}, {e.category or e.genre or 'n/a'}, {'international' if e.is_international else 'India'}"
                    f"{', home ' + e.home_city if e.home_city else ''}]: composite {_f(m.composite_score,1)}, google trend {_f(m.google_trend_score)}, "
                    f"spotify monthly listeners {m.spotify_monthly_listeners if m.spotify_monthly_listeners is not None else 'n/a'}, "
                    f"instagram followers {m.instagram_followers if m.instagram_followers is not None else 'n/a'}, {fee}"
                )
            sources.append(("Artist metrics: " + ", ".join(e.name for e, _ in picked)) if picked else "Top artists by composite score")

        # Events
        now = datetime.now(timezone.utc)
        ev_q = (
            select(Event.title, Event.event_date, Event.category, Event.source, Event.status, Event.ticket_price_min, Event.ticket_price_max, Venue.name, Venue.city)
            .outerjoin(Venue, Event.venue_id == Venue.id)
        )
        total_events = await db.scalar(select(func.count(Event.id))) or 0
        upcoming_n = await db.scalar(select(func.count(Event.id)).where(Event.event_date >= now)) or 0
        ev_rows = []
        if mentioned:
            for c in mentioned[:2]:
                like = f"%{c.name}%"
                ev_rows += (await db.execute(
                    ev_q.where(Event.event_date >= now, (Venue.city.ilike(c.name)) | (Event.title.ilike(like)))
                    .order_by(Event.event_date.asc()).limit(8)
                )).all()
        if not ev_rows:
            ev_rows = (await db.execute(ev_q.where(Event.event_date >= now).order_by(Event.event_date.asc()).limit(10))).all()
        label = "Next events"
        if not ev_rows:
            ev_rows = (await db.execute(ev_q.order_by(Event.event_date.desc()).limit(10))).all()
            label = "Most recent tracked events (none are in the future)"
        lines.append(f"\nEVENTS TRACKED: {total_events} total, {upcoming_n} dated in the future. {label}:")
        for t, d, cat, src, st, pmin, pmax, vn, vc in ev_rows[:14]:
            price = f"{inr_short(pmin)}–{inr_short(pmax)}" if pmin is not None and pmax is not None else (inr_short(pmin) if pmin is not None else "price n/a")
            lines.append(f"- {t} | {d.astimezone(timezone.utc).strftime('%d %b %Y') if d else 'date n/a'} | {vn or 'venue n/a'}{', ' + vc if vc else ''} | {cat or 'n/a'} | {price} | source {src}")
        sources.append(f"Events ({total_events} tracked, {upcoming_n} upcoming)")

        # Venues for mentioned cities
        for c in mentioned[:2]:
            vs = (await db.execute(select(Venue.name, Venue.total_capacity, Venue.venue_type).where(Venue.city.ilike(c.name)).order_by(Venue.total_capacity.desc().nullslast()).limit(10))).all()
            if vs:
                lines.append(f"\nVENUES IN {c.name.upper()} (by capacity):")
                for n, cap, vt in vs:
                    lines.append(f"- {n}: capacity {cap if cap is not None else 'n/a'}, type {vt or 'n/a'}")
                sources.append(f"Venue capacities: {c.name}")

        if any(k in q for k in ("price", "pricing", "ticket", "₹", "rs ", "rupee", "cost")):
            from app.api.routes.pricing import CATEGORY_BENCHMARKS, CITY_PRICE_MULTIPLIERS
            lines.append("\nTICKET PRICE BENCHMARKS (₹ per ticket by category):")
            for k, b in CATEGORY_BENCHMARKS.items():
                lines.append(f"- {k}: floor {b['floor']}, sweet spot {b['sweet_spot']}, premium {b['premium']}, ultra-premium {b['ultra_premium']}")
            lines.append("City price multipliers: " + ", ".join(f"{k} x{v}" for k, v in CITY_PRICE_MULTIPLIERS.items()))
            sources.append("Ticket price benchmarks")
    except Exception as exc:  # grounding is best-effort
        logger.warning("copilot_context failed", error=str(exc))
        try:
            await db.rollback()
        except Exception:
            pass
    if not lines:
        return "", []
    return "\n\nLIVE DATA (queried " + datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC") + "):\n" + "\n".join(lines), sources

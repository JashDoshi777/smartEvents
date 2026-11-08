"""
LiveIQ — Shared upsert logic for scraped events (District, BookMyShow).
Normalizes scraper output into the events table, resolving venue_name +
city to a real Venue row where possible (falls back to NULL venue_id if
no match — never fabricates one).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.event import Event
from app.models.entity import Entity
from app.models.venue import Venue

logger = structlog.get_logger()


# Source spellings -> our tracked city names (NCR / MMR satellites roll up to the metro we track).
CITY_CANONICAL = {
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru", "gurgaon": "Delhi NCR", "gurugram": "Delhi NCR",
    "noida": "Delhi NCR", "new delhi": "Delhi NCR", "delhi": "Delhi NCR", "ghaziabad": "Delhi NCR",
    "faridabad": "Delhi NCR", "greater noida": "Delhi NCR", "navi mumbai": "Mumbai", "thane": "Mumbai",
    "bombay": "Mumbai", "calcutta": "Kolkata", "madras": "Chennai", "mysore": "Mysuru", "mangalore": "Mangaluru",
    "trivandrum": "Thiruvananthapuram", "panaji": "Goa", "panjim": "Goa", "allahabad": "Prayagraj",
    "cochin": "Kochi", "baroda": "Vadodara", "vizag": "Visakhapatnam",
}


def canonical_city(city: Optional[str]) -> Optional[str]:
    if not city:
        return None
    c = " ".join(city.replace("-", " ").split())
    return CITY_CANONICAL.get(c.lower(), c)


async def _resolve_venue(session, venue_name: Optional[str], city: Optional[str]) -> Optional[UUID]:
    """Match a scraped venue_name + city against the real venues table.

    Links only when the match is UNAMBIGUOUS (exactly one venue in that city whose name contains the
    scraped name, or equals it); ambiguous or missing -> NULL rather than a guess."""
    city = canonical_city(city)
    if not venue_name or not city or len(venue_name.strip()) < 4:
        return None
    result = await session.execute(
        select(Venue.id, Venue.name).where(
            Venue.city.ilike(city),
            Venue.name.ilike(f"%{venue_name.strip()}%"),
        ).limit(3)
    )
    rows = result.all()
    if len(rows) == 1:
        return rows[0][0]
    exact = [r[0] for r in rows if r[1].lower() == venue_name.strip().lower()]
    return exact[0] if len(exact) == 1 else None


async def _resolve_entity(session, title: str) -> Optional[UUID]:
    """
    Best-effort link from an event title to an existing entity.
    Requires the entity's FULL name to appear in the title (not just any
    single word in common) — matching on any word in title.split() would
    let a title like "Grand Diwali Night Live" false-positive against an
    unrelated entity whose name happens to contain "Grand" or "Night",
    silently mis-attributing the event. Falls back to no match (NULL
    entity_id) rather than guess when the title is too short/generic.
    """
    title_lower = title.lower()
    # Loads all entity names and matches in Python — fine at today's scale
    # (dozens of entities); would need a SQL-side substring/trigram approach
    # if the entities table grows into the thousands.
    # Longest name first so a more specific match wins over a short one
    # that happens to also be a substring (e.g. "Rahman" vs "AR Rahman").
    result = await session.execute(
        select(Entity.id, Entity.name)
        .where(Entity.name.isnot(None))
    )
    candidates = [(str(eid), name) for eid, name in result.all() if name and len(name) > 3]
    candidates.sort(key=lambda c: len(c[1]), reverse=True)

    for entity_id, name in candidates:
        if name.lower() in title_lower:
            return entity_id
    return None


async def upsert_scraped_events(events_raw: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Upsert normalized scraper output (from district_scraper or
    bookmyshow_scraper) into the events table. Idempotent via
    ON CONFLICT (external_id, source) DO UPDATE.

    inserted/updated are reported separately (via RETURNING xmax = 0, the
    Postgres idiom for "this row was inserted, not updated, by this
    statement") — a single "inserted" counter that actually mixes both
    would make re-runs look like new events every time a scraper re-scrapes
    the same live listings, corrupting any dashboard/monitoring built on it.
    """
    inserted = 0
    updated = 0
    skipped = 0
    errors = 0

    async with AsyncSessionLocal() as session:
        async with session.begin():
            for raw in events_raw:
                if not raw.get("external_id") or not raw.get("title"):
                    skipped += 1
                    continue
                if not raw.get("event_date"):
                    # Event.event_date is NOT NULL — an event with an
                    # unparseable/missing date (e.g. "To be announced", or a
                    # BMS card scraped without fetch_real_dates) can't be
                    # stored without fabricating a date. Skip rather than guess.
                    skipped += 1
                    continue

                try:
                    venue_id = await _resolve_venue(session, raw.get("venue_name"), raw.get("city"))
                    entity_id = await _resolve_entity(session, raw["title"])
                    now = raw.get("scraped_at") or datetime.now(timezone.utc)

                    # Optional real demand-signal fields — only PredictHQ
                    # (via predicthq_sync.py) populates these; every other
                    # scraper source omits them, so they stay NULL, never
                    # a fabricated zero.
                    values = dict(
                        external_id=raw["external_id"],
                        source=raw["source"],
                        title=raw["title"],
                        category=raw.get("category", "music"),
                        event_date=raw["event_date"],
                        ticket_price_min=raw.get("ticket_price_min"),
                        ticket_price_max=raw.get("ticket_price_max"),
                        booking_url=raw.get("booking_url"),
                        cover_image_url=raw.get("cover_image_url"),
                        status=raw.get("status", "upcoming"),
                        entity_id=entity_id,
                        venue_id=venue_id,
                        city=canonical_city(raw.get("city")),
                        venue_name_raw=(raw.get("venue_name") or None) and raw["venue_name"][:255],
                        scraped_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                    update_set = {
                        "title": raw["title"],
                        "ticket_price_min": raw.get("ticket_price_min"),
                        "ticket_price_max": raw.get("ticket_price_max"),
                        "status": raw.get("status", "upcoming"),
                        "venue_id": venue_id,
                        "city": canonical_city(raw.get("city")),
                        "venue_name_raw": (raw.get("venue_name") or None) and raw["venue_name"][:255],
                        "entity_id": entity_id,
                        "updated_at": now,
                    }
                    for field in ("predicthq_rank", "predicthq_local_rank", "predicthq_predicted_attendance"):
                        if field in raw:
                            values[field] = raw[field]
                            update_set[field] = raw[field]

                    stmt = pg_insert(Event).values(**values).on_conflict_do_update(
                        constraint="uq_event_external_source",
                        set_=update_set,
                    ).returning(literal_column("(xmax = 0)").label("was_inserted"))
                    result = await session.execute(stmt)
                    row = result.first()
                    if row is not None and row.was_inserted:
                        inserted += 1
                    else:
                        updated += 1
                except Exception as exc:
                    logger.warning("scraped_event_upsert: upsert error", error=str(exc), title=raw.get("title"))
                    errors += 1

    return {"inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors}

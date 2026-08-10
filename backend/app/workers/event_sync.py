"""
LiveIQ — Event Sync Worker (Sprint 4 — DB Write)
=================================================
Pulls upcoming events from Ticketmaster for Indian cities and upserts them
into the NeonDB `events` table so the frontend can display real data.

Schedule: every 4 hours (see celery_app.py beat_schedule)

Improvements over the Sprint 1 stub:
 - Actually writes to PostgreSQL (was TODO)
 - Normalises Ticketmaster payload → Event ORM model
 - Tries to link event → entity by name fuzzy match
 - Idempotent: ON CONFLICT (external_id, source) DO UPDATE
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from celery import Task
from sqlalchemy import select, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.workers.celery_app import celery_app
from app.workers.run_utils import run_async
from app.services.ingestion.ticketmaster_client import TicketmasterClient
from app.core.database import AsyncSessionLocal
from app.models.event import Event
from app.models.entity import Entity

logger = structlog.get_logger()

# ── Constants ─────────────────────────────────────────────────────────────────

INDIA_CITIES = [
    "Mumbai", "Delhi", "Bengaluru", "Hyderabad",
    "Chennai", "Kolkata", "Pune", "Ahmedabad",
    "Jaipur", "Chandigarh", "Kochi", "Indore",
]

TM_CLASSIFICATIONS = ["Music", "Comedy", "Sports", "Arts & Theatre"]

CATEGORY_MAP: Dict[str, str] = {
    "Music":          "music",
    "Comedy":         "comedy",
    "Sports":         "sports",
    "Arts & Theatre": "theatre",
    "Theatre":        "theatre",
    "Film":           "movie",
}

SOURCE = "ticketmaster"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_price(price_ranges: Optional[List[Dict]]) -> tuple[Optional[float], Optional[float]]:
    """Extract min/max ticket price from Ticketmaster priceRanges."""
    if not price_ranges:
        return None, None
    mins, maxs = [], []
    for pr in price_ranges:
        if pr.get("currency", "INR") == "INR":
            if pr.get("min") is not None:
                mins.append(float(pr["min"]))
            if pr.get("max") is not None:
                maxs.append(float(pr["max"]))
    return (min(mins) if mins else None), (max(maxs) if maxs else None)


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a Ticketmaster ISO date string."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _normalise_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Map a raw Ticketmaster event dict → flat dict matching the Event model columns.
    Returns None if the event is missing a title or date.
    """
    title = raw.get("name")
    if not title:
        return None

    # Dates
    dates = raw.get("dates", {})
    start = dates.get("start", {})
    event_dt = _parse_date(start.get("dateTime") or start.get("localDate"))
    if not event_dt:
        return None

    # Venue
    venues_raw = (raw.get("_embedded") or {}).get("venues", [{}])
    venue_raw = venues_raw[0] if venues_raw else {}
    venue_name = venue_raw.get("name")
    city_name  = (venue_raw.get("city") or {}).get("name")

    # Category
    classifs = raw.get("classifications", [{}])
    genre = (classifs[0].get("segment") or {}).get("name", "Music")
    category = CATEGORY_MAP.get(genre, "music")

    # Price
    price_min, price_max = _parse_price(raw.get("priceRanges"))

    # Images
    images = raw.get("images", [])
    cover_url = next((img["url"] for img in images if img.get("ratio") == "16_9" and img.get("width", 0) >= 640), None)

    return {
        "external_id":      raw.get("id"),
        "source":           SOURCE,
        "title":            title,
        "category":         category,
        "event_date":       event_dt,
        "venue_name":       venue_name,  # raw — not a FK yet
        "city":             city_name,
        "ticket_price_min": price_min,
        "ticket_price_max": price_max,
        "booking_url":      raw.get("url"),
        "cover_image_url":  cover_url,
        "status":           "upcoming",
        "scraped_at":       datetime.now(timezone.utc),
    }


async def _resolve_entity(session, title: str) -> Optional[UUID]:
    """
    Try to link an event title to an existing entity.
    Simple substring match — good enough for now.
    """
    words = [w for w in title.lower().split() if len(w) > 3]
    if not words:
        return None

    result = await session.execute(
        select(Entity.id).where(
            or_(*[Entity.name.ilike(f"%{w}%") for w in words[:3]])
        ).limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def _upsert_events(events_raw: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Upsert normalised events into the PostgreSQL events table.
    Uses ON CONFLICT DO UPDATE to stay idempotent.
    """
    inserted = 0
    skipped  = 0
    errors   = 0

    async with AsyncSessionLocal() as session:
        async with session.begin():
            for raw in events_raw:
                norm = _normalise_event(raw)
                if not norm:
                    skipped += 1
                    continue

                entity_id = await _resolve_entity(session, norm["title"])

                try:
                    stmt = pg_insert(Event).values(
                        external_id      = norm["external_id"],
                        source           = norm["source"],
                        title            = norm["title"],
                        category         = norm["category"],
                        event_date       = norm["event_date"],
                        ticket_price_min = norm["ticket_price_min"],
                        ticket_price_max = norm["ticket_price_max"],
                        booking_url      = norm["booking_url"],
                        cover_image_url  = norm["cover_image_url"],
                        status           = norm["status"],
                        entity_id        = entity_id,
                        scraped_at       = norm["scraped_at"],
                        created_at       = norm["scraped_at"],
                        updated_at       = norm["scraped_at"],
                    ).on_conflict_do_update(
                        constraint="uq_event_external_source",
                        set_={
                            "title":            norm["title"],
                            "ticket_price_min": norm["ticket_price_min"],
                            "ticket_price_max": norm["ticket_price_max"],
                            "status":           norm["status"],
                            "updated_at":       norm["scraped_at"],
                            "entity_id":        entity_id,
                        }
                    )
                    await session.execute(stmt)
                    inserted += 1
                except Exception as exc:
                    logger.warning("event_sync: upsert error", error=str(exc), title=norm.get("title"))
                    errors += 1

    return {"inserted": inserted, "skipped": skipped, "errors": errors}


async def _run_sync() -> Dict[str, Any]:
    """
    Main async sync pipeline:
      1. Pull events from Ticketmaster for each Indian city + classification
      2. Deduplicate by external_id
      3. Upsert to PostgreSQL
    """
    all_raw: List[Dict[str, Any]] = []
    seen_ids: set = set()

    async with TicketmasterClient() as client:
        tasks = [
            client.search_events(
                classification_name=clf,
                country_code="IN",
                size=50,
            )
            for clf in TM_CLASSIFICATIONS
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for clf, result in zip(TM_CLASSIFICATIONS, results):
        if isinstance(result, Exception):
            logger.warning("event_sync: Ticketmaster fetch failed", classification=clf, error=str(result))
            continue

        events = result.get("events", [])
        for ev in events:
            eid = ev.get("id")
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                all_raw.append(ev)

        logger.info("event_sync: fetched events", classification=clf, count=len(events))

    if not all_raw:
        return {"status": "no_events", "total_fetched": 0}

    db_result = await _upsert_events(all_raw)
    logger.info(
        "event_sync: upsert complete",
        fetched=len(all_raw),
        **db_result,
    )

    completed_count = await _mark_past_events_completed()

    return {
        "status":        "ok",
        "total_fetched": len(all_raw),
        "marked_completed": completed_count,
        "synced_at":     datetime.now(timezone.utc).isoformat(),
        **db_result,
    }


async def _mark_past_events_completed() -> int:
    """
    Real event-lifecycle fix: nothing previously transitioned an event's
    status once its date passed, so every synced event stayed 'upcoming'
    (or whatever status it last had) forever, even years after the fact.
    No current route actually filters on Event.status (they all use
    real event_date ranges instead), so this was dormant rather than
    visibly broken — but the column exists and is meant to reflect
    reality, so it should. CANCELLED/POSTPONED are left alone since
    those are real, source-reported outcomes this worker has no basis
    to override.
    """
    from sqlalchemy import update as sa_update
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa_update(Event)
            .where(
                Event.event_date < now,
                Event.status.in_(["upcoming", "on_sale", "filling_fast", "sold_out"]),
            )
            .values(status="completed")
        )
        await session.commit()
        return result.rowcount or 0


# ── Celery Task ───────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.workers.event_sync.sync_upcoming_events",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def sync_upcoming_events(self: Task):
    """
    Entry point: sync upcoming events from Ticketmaster → NeonDB.
    Runs every 4 hours via Celery Beat.
    """
    logger.info("event_sync: starting sync cycle")
    try:
        result = run_async(_run_sync())
        logger.info("event_sync: cycle complete", **result)
        return result
    except Exception as exc:
        logger.error("event_sync: cycle failed", error=str(exc))
        raise self.retry(exc=exc)

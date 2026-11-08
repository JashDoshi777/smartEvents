"""
LiveIQ — Venue Availability Calendar (Sprint 7C)
Weekend-by-weekend heatmap of a venue's real booked dates vs open dates,
built from actual Event rows linked to that venue — no fabricated or
inferred bookings. Every "open" weekend is genuinely "no tracked event
found," not "confirmed available" (this platform doesn't have live
venue-management data, only what's been scraped/synced into `events`).

All week/weekend bucketing is done in IST (Asia/Kolkata, UTC+05:30): an event stored as
Sunday 19:30 UTC is 1:00 am Monday in India and must not count toward the weekend.

Endpoints:
  GET /venues/{venue_id}/calendar?months=3
  GET /venues/availability?city=Mumbai&min_capacity=1000&months=3   → venues with open weekends
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.venue import Venue
from app.models.event import Event
from app.api.deps import get_current_user
from app.models.user import User
from app.services.city_lookup import escape_like, norm_city

router = APIRouter()
logger = structlog.get_logger()

IST = ZoneInfo("Asia/Kolkata")
DATA_NOTE = (
    "\"Open\" means no tracked event was found for that weekend in this platform's events data "
    "(District, BookMyShow, Ticketmaster, PredictHQ sources) — it is NOT a confirmed live availability "
    "check with the venue itself, since no such integration exists. Venues with sparse event coverage "
    "will show mostly \"open\" weekends; this reflects current data coverage, not necessarily true availability."
)


def _week_start(d: datetime) -> datetime:
    """Monday 00:00 IST of the week containing d (tz-aware, IST)."""
    d_ist = d.astimezone(IST)
    d0 = d_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return d0 - timedelta(days=d0.weekday())


def _ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def _is_weekend(dt_ist: datetime) -> bool:
    return dt_ist.weekday() >= 4  # Fri, Sat, Sun


@router.get("/availability", summary="Venues in a city with open (untracked) weekends in the next N months")
async def find_open_weekends(
    city: str = Query(..., min_length=1, max_length=100),
    min_capacity: int = Query(0, ge=0, le=200000),
    months: int = Query(3, ge=1, le=12),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    range_start = _week_start(now)
    range_end = range_start + timedelta(weeks=months * 4)

    vstmt = select(Venue).where(Venue.city.ilike(escape_like(norm_city(city)), escape="\\"))
    if min_capacity:
        vstmt = vstmt.where(Venue.total_capacity >= min_capacity)
    venues = (await db.execute(vstmt.order_by(Venue.total_capacity.desc().nullslast(), Venue.name))).scalars().all()
    ids = [v.id for v in venues]

    booked: dict = {v.id: set() for v in venues}
    if ids:
        rows = (await db.execute(
            select(Event.venue_id, Event.event_date)
            .where(Event.venue_id.in_(ids), Event.event_date >= range_start, Event.event_date < range_end)
        )).all()
        for vid, dt in rows:
            d = _ist(dt)
            if _is_weekend(d):
                booked[vid].add((d - timedelta(days=d.weekday())).date())

    all_weeks = []
    c = range_start
    while c < range_end:
        all_weeks.append(c.date())
        c += timedelta(days=7)
    this_week = _week_start(now).date()
    # a weekend that is already over is not "available": only count weekends whose Sunday hasn't ended
    today_ist = now.astimezone(IST).date()
    future_weeks = [w for w in all_weeks if w + timedelta(days=6) >= today_ist]

    out = []
    for v in venues:
        free = [w for w in future_weeks if w not in booked[v.id]]
        out.append({
            "id": str(v.id),
            "name": v.name,
            "city": v.city,
            "capacity": v.total_capacity,
            "open_weekends": [(w + timedelta(days=4)).isoformat() for w in free],   # Friday of each open weekend
            "open_count": len(free),
            "booked_count": len(future_weeks) - len(free),
            "total_weekends": len(future_weeks),
        })
    out.sort(key=lambda r: (-r["open_count"], -(r["capacity"] or 0), r["name"]))
    return {
        "city": city,
        "min_capacity": min_capacity,
        "range": {"start": range_start.date().isoformat(), "end": range_end.date().isoformat(), "months": months},
        "total": len(out),
        "venues": out[:limit],
        "data_note": DATA_NOTE,
        "timezone": "Asia/Kolkata",
    }


@router.get("/{venue_id}/calendar", summary="Weekend-by-weekend booked/open calendar for a venue")
async def get_venue_calendar(
    venue_id: str,
    months: int = Query(3, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        uid = UUID(venue_id)
    except ValueError:
        raise HTTPException(400, "Invalid venue_id format")

    venue = await db.scalar(select(Venue).where(Venue.id == uid))
    if venue is None:
        raise HTTPException(404, f"Venue '{venue_id}' not found")

    now = datetime.now(timezone.utc)
    range_start = _week_start(now)
    range_end = range_start + timedelta(weeks=months * 4)  # approx month = 4 weeks, real week boundaries throughout

    events_result = await db.execute(
        select(Event.id, Event.title, Event.event_date, Event.status, Event.source)
        .where(Event.venue_id == uid, Event.event_date >= range_start, Event.event_date < range_end)
        .order_by(Event.event_date)
    )
    events = events_result.all()

    # Bucket real events into their weekend (Fri-Sun IST of that week — the commercially
    # relevant "weekend" for ticketed live events, not the Mon-Sun week itself).
    weeks = []
    cursor = range_start
    while cursor < range_end:
        week_end = cursor + timedelta(days=7)

        week_events = []
        weekend_events = []
        for e in events:
            d = _ist(e.event_date)
            if not (cursor <= d < week_end):
                continue
            item = {
                "id": str(e.id),
                "title": e.title,
                "event_date": e.event_date.isoformat(),
                "event_date_ist": d.isoformat(),
                "status": e.status,
                "source": e.source,
            }
            week_events.append(item)
            if _is_weekend(d):
                weekend_events.append(item)

        weeks.append({
            "week_start": cursor.date().isoformat(),
            "week_end": (week_end - timedelta(days=1)).date().isoformat(),
            "events_this_week": week_events,
            "weekend_events": weekend_events,
            "is_weekend_booked": len(weekend_events) > 0,
            "is_booked": len(week_events) > 0,
        })
        cursor = week_end

    total_weekend_events = sum(len(w["weekend_events"]) for w in weeks)
    booked_weekends = sum(1 for w in weeks if w["is_weekend_booked"])

    return {
        "venue": {
            "id": str(venue.id),
            "name": venue.name,
            "city": venue.city,
            "capacity": venue.total_capacity,
        },
        "range": {"start": range_start.date().isoformat(), "end": range_end.date().isoformat(), "months": months},
        "timezone": "Asia/Kolkata",
        "weeks": weeks,
        "summary": {
            "total_weeks": len(weeks),
            "booked_weekends": booked_weekends,
            "open_weekends": len(weeks) - booked_weekends,
            "total_tracked_events": total_weekend_events,
        },
        "data_note": DATA_NOTE,
    }

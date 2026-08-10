"""
LiveIQ — Venue Availability Calendar (Sprint 7C)
Weekend-by-weekend heatmap of a venue's real booked dates vs open dates,
built from actual Event rows linked to that venue — no fabricated or
inferred bookings. Every "open" weekend is genuinely "no tracked event
found," not "confirmed available" (this platform doesn't have live
venue-management data, only what's been scraped/synced into `events`).

Endpoint:
  GET /venues/{venue_id}/calendar?months=3
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.venue import Venue
from app.models.event import Event
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()


def _week_start(d: datetime) -> datetime:
    """Monday of the week containing d, at midnight UTC."""
    d0 = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return d0 - timedelta(days=d0.weekday())


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

    # Bucket real events into their weekend (Fri-Sun of that ISO week —
    # the commercially relevant "weekend" for ticketed live events, not
    # the calendar Mon-Sun week itself).
    weeks = []
    cursor = range_start
    while cursor < range_end:
        week_end = cursor + timedelta(days=7)
        friday = cursor + timedelta(days=4)
        sunday = cursor + timedelta(days=6, hours=23, minutes=59, seconds=59)

        week_events = [
            {
                "id": str(e.id),
                "title": e.title,
                "event_date": e.event_date.isoformat(),
                "status": e.status,
                "source": e.source,
            }
            for e in events
            if cursor <= e.event_date < week_end
        ]
        weekend_events = [we for we in week_events if friday <= datetime.fromisoformat(we["event_date"]) <= sunday]

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
        "weeks": weeks,
        "summary": {
            "total_weeks": len(weeks),
            "booked_weekends": booked_weekends,
            "open_weekends": len(weeks) - booked_weekends,
            "total_tracked_events": total_weekend_events,
        },
        "data_note": (
            "\"Open\" means no tracked event was found for that weekend in this platform's events data "
            "(District, BookMyShow, Ticketmaster, PredictHQ sources) — it is NOT a confirmed live availability "
            "check with the venue itself, since no such integration exists. Venues with sparse event coverage "
            "will show mostly \"open\" weekends; this reflects current data coverage, not necessarily true availability."
        ),
    }

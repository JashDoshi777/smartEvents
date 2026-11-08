"""
LiveIQ — Notifications (Sprint 5D, per-user read state added Sprint 7B)
Persistent, stateful version of the signal detection already used by
/dashboard/alerts — stored in the existing TrendSignal table (Postgres,
not MongoDB) so notifications have stable IDs and real read/unread state
survive across page loads, independent of MongoDB's availability.

Signal generation runs as a scheduled worker (app/workers/notification_signals.py,
every 15 min) — these routes are pure reads/writes. Generation used to run
inline on every GET here, which meant two reads racing each other (e.g. the
bell badge and the dropdown list loading a few seconds apart) could each
independently insert signals, leaving the badge count and the list
observing different states depending on which read happened to trigger
generation last.

Read state: TrendSignal.is_read USED to be a single global column shared
by every user — Sprint 7A introduced real multi-user auth and exposed this
as a live bug (User A marking a signal read hid it for User B too). Read
state is now tracked per (user_id, trend_signal_id) in a separate
NotificationRead table; TrendSignal.is_read is no longer read or written
by these routes (left in place on the model only for other code paths
that may still reference it, e.g. the anomaly-detection worker that
creates rows — it simply goes unused as a "read" signal going forward).

Endpoints:
  GET  /notifications              → list, newest first
  GET  /notifications/unread-count → badge count for the bell icon
  POST /notifications/{id}/read    → mark one as read (for the current user)
  POST /notifications/read-all     → mark all as read (for the current user)
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, exists, func, literal, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AutocommitSessionLocal, get_db, run_queries
from app.models.entity import Entity
from app.models.intelligence import TrendSignal
from app.models.user_data import NotificationRead, Watchlist
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()


def _current_signals():
    """One row per (entity, signal_type): the NEWEST signal. The generator
    re-emits the same breakout/news signal over time (14 rows -> 9 distinct
    in prod data), so listing every row showed duplicates and inflated the
    unread badge. Both the list and the badge count use this same set, so they
    can never disagree."""
    sub = (
        select(TrendSignal)
        .distinct(TrendSignal.entity_id, TrendSignal.signal_type)
        .order_by(TrendSignal.entity_id, TrendSignal.signal_type, TrendSignal.detected_at.desc())
        .subquery("current_signals")
    )
    from sqlalchemy.orm import aliased
    return aliased(TrendSignal, sub)


def _read_exists(sig, user_id):
    return exists().where(and_(NotificationRead.user_id == user_id, NotificationRead.trend_signal_id == sig.id))


def _to_dict(sig: TrendSignal, entity_name: str | None, is_read: bool, is_watched: bool) -> dict:
    return {
        "id": str(sig.id),
        "type": sig.signal_type,
        "title": sig.alert_message.split(" — ")[0] if sig.alert_message and " — " in sig.alert_message else sig.alert_message,
        "message": sig.alert_message,
        "entity": entity_name,
        "severity": sig.severity,
        "is_read": is_read,
        "is_watched": is_watched,
        "detected_at": sig.detected_at.isoformat() if sig.detected_at else None,
    }


@router.get("", summary="List notifications, newest first — watchlisted entities surfaced first")
async def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One query: read/watched flags are EXISTS sub-selects, ordering is
    watched-first then newest-first, applied in SQL so pagination is exact
    (the previous version merged two capped fetches in Python)."""
    sig = _current_signals()
    is_read = _read_exists(sig, user.id).label("is_read")
    is_watched = exists().where(and_(Watchlist.user_id == user.id, Watchlist.entity_id == sig.entity_id)).label("is_watched")
    stmt = (
        select(sig, Entity.name, is_read, is_watched)
        .outerjoin(Entity, Entity.id == sig.entity_id)
    )
    if unread_only:
        stmt = stmt.where(~_read_exists(sig, user.id))
    stmt = stmt.order_by(is_watched.desc(), sig.detected_at.desc().nullslast(), sig.id).limit(limit).offset(offset)

    rows = (await db.execute(stmt)).all()
    return {
        "notifications": [_to_dict(r[0], r[1], bool(r[2]), bool(r[3])) for r in rows],
        "total": len(rows),
        "offset": offset,
    }


@router.get("/unread-count", summary="Unread notification count for the bell badge")
async def get_unread_count(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    sig = _current_signals()
    count = await db.scalar(select(func.count()).select_from(sig).where(~_read_exists(sig, user.id)))
    return {"unread_count": count or 0}


@router.post("/read-all", summary="Mark all notifications as read")
async def mark_all_read(user: User = Depends(get_current_user)):
    """Single INSERT .. SELECT (atomic by itself, so it runs in autocommit: 1 round-trip)."""
    sig = _current_signals()
    # id/read_at have only Python-side defaults (a single shared constant under
    # INSERT..SELECT -> PK collisions), so generate them in SQL per row.
    unread = select(literal(user.id, type_=PG_UUID(as_uuid=True)), sig.id, func.gen_random_uuid(), func.now()).where(~_read_exists(sig, user.id))
    stmt = pg_insert(NotificationRead).from_select(["user_id", "trend_signal_id", "id", "read_at"], unread, include_defaults=False)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_notification_read_user_signal")
    async with AutocommitSessionLocal() as s:
        result = await s.execute(stmt)
    return {"status": "ok", "marked_read": max(result.rowcount or 0, 0)}


@router.post("/{notification_id}/read", summary="Mark one notification as read")
async def mark_read(notification_id: str, user: User = Depends(get_current_user)):
    try:
        uid = UUID(notification_id)
    except (ValueError, AttributeError):
        raise HTTPException(400, "Invalid notification_id format")

    # INSERT .. SELECT from trend_signals: inserts only if the signal exists;
    # ON CONFLICT DO NOTHING makes re-marking idempotent.
    unread = select(literal(user.id, type_=PG_UUID(as_uuid=True)), TrendSignal.id, func.gen_random_uuid(), func.now()).where(TrendSignal.id == uid)
    stmt = pg_insert(NotificationRead).from_select(["user_id", "trend_signal_id", "id", "read_at"], unread, include_defaults=False)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_notification_read_user_signal")
    async with AutocommitSessionLocal() as s:
        result = await s.execute(stmt)
        if (result.rowcount or 0) == 0:
            known = await s.scalar(select(TrendSignal.id).where(TrendSignal.id == uid))
            if known is None:
                raise HTTPException(404, f"Notification '{notification_id}' not found")
    return {"status": "ok", "id": notification_id}

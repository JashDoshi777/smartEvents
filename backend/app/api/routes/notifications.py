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
from sqlalchemy import select, desc, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.intelligence import TrendSignal
from app.models.user_data import NotificationRead, Watchlist
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()


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
    limit: int = Query(20, le=100),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    read_subq = (
        select(NotificationRead.trend_signal_id)
        .where(NotificationRead.user_id == user.id)
        .scalar_subquery()
    )

    watched_result = await db.execute(select(Watchlist.entity_id).where(Watchlist.user_id == user.id))
    watched_entity_ids = {r for (r,) in watched_result.all()}

    # Pull enough recency-ordered rows to re-sort watched-first before
    # truncating to `limit`. This window alone isn't sufficient: a watched
    # entity's signal older than the window would never surface even though
    # it's exactly what "priority" alerts are for. So watched-entity signals
    # are ALSO fetched directly (unbounded by recency, only by unread_only),
    # and merged in below — capped at 500 so this stays bounded even if
    # TrendSignal grows large.
    fetch_cap = min(limit * 10, 500)
    recent_stmt = (
        select(TrendSignal, Entity.name)
        .outerjoin(Entity, Entity.id == TrendSignal.entity_id)
        .order_by(desc(TrendSignal.detected_at))
        .limit(fetch_cap)
    )
    if unread_only:
        recent_stmt = recent_stmt.where(TrendSignal.id.not_in(read_subq))

    recent_result = await db.execute(recent_stmt)
    rows = list(recent_result.all())

    if watched_entity_ids:
        watched_stmt = (
            select(TrendSignal, Entity.name)
            .outerjoin(Entity, Entity.id == TrendSignal.entity_id)
            .where(TrendSignal.entity_id.in_(watched_entity_ids))
            .order_by(desc(TrendSignal.detected_at))
            .limit(fetch_cap)
        )
        if unread_only:
            watched_stmt = watched_stmt.where(TrendSignal.id.not_in(read_subq))

        watched_signal_result = await db.execute(watched_stmt)
        seen_ids = {sig.id for sig, _ in rows}
        for sig, name in watched_signal_result.all():
            if sig.id not in seen_ids:
                rows.append((sig, name))
                seen_ids.add(sig.id)

    # Batch-fetch this user's read signal ids so is_read can be computed
    # without a per-row query.
    signal_ids = [sig.id for sig, _ in rows]
    read_ids: set = set()
    if signal_ids:
        read_result = await db.execute(
            select(NotificationRead.trend_signal_id)
            .where(NotificationRead.user_id == user.id, NotificationRead.trend_signal_id.in_(signal_ids))
        )
        read_ids = {r for (r,) in read_result.all()}

    # Watched-entity signals first, each group still newest-first: the
    # merged list isn't globally sorted by detected_at anymore (the watched
    # signals appended above may be older than the last "recent" row), so
    # explicitly sort by detected_at within each group instead of relying on
    # Python's stable-sort-preserves-input-order (which only worked when the
    # input was already fully time-ordered).
    def sort_key(row):
        sig, _ = row
        watched_rank = 0 if sig.entity_id in watched_entity_ids else 1
        return (watched_rank, -(sig.detected_at.timestamp() if sig.detected_at else 0))

    rows.sort(key=sort_key)
    rows = rows[:limit]

    return {
        "notifications": [
            _to_dict(sig, name, sig.id in read_ids, sig.entity_id in watched_entity_ids)
            for sig, name in rows
        ],
        "total": len(rows),
    }


@router.get("/unread-count", summary="Unread notification count for the bell badge")
async def get_unread_count(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    read_subq = (
        select(NotificationRead.trend_signal_id)
        .where(NotificationRead.user_id == user.id)
        .scalar_subquery()
    )
    count = await db.scalar(
        select(func.count(TrendSignal.id)).where(TrendSignal.id.not_in(read_subq))
    )
    return {"unread_count": count or 0}


@router.post("/{notification_id}/read", summary="Mark one notification as read")
async def mark_read(notification_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        uid = UUID(notification_id)
    except ValueError:
        raise HTTPException(400, "Invalid notification_id format")

    exists = await db.scalar(select(TrendSignal.id).where(TrendSignal.id == uid))
    if exists is None:
        raise HTTPException(404, f"Notification '{notification_id}' not found")

    # ON CONFLICT DO NOTHING — marking an already-read signal read again is
    # a no-op, not an error (the unique constraint would otherwise raise).
    stmt = pg_insert(NotificationRead).values(user_id=user.id, trend_signal_id=uid)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_notification_read_user_signal")
    await db.execute(stmt)
    await db.commit()
    return {"status": "ok", "id": notification_id}


@router.post("/read-all", summary="Mark all notifications as read")
async def mark_all_read(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    read_subq = (
        select(NotificationRead.trend_signal_id)
        .where(NotificationRead.user_id == user.id)
        .scalar_subquery()
    )
    unread_result = await db.execute(
        select(TrendSignal.id).where(TrendSignal.id.not_in(read_subq))
    )
    unread_ids = [r for (r,) in unread_result.all()]

    if unread_ids:
        stmt = pg_insert(NotificationRead).values(
            [{"user_id": user.id, "trend_signal_id": sid} for sid in unread_ids]
        )
        stmt = stmt.on_conflict_do_nothing(constraint="uq_notification_read_user_signal")
        await db.execute(stmt)
        await db.commit()

    return {"status": "ok", "marked_read": len(unread_ids)}

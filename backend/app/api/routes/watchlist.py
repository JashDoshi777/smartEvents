"""
LiveIQ — Watchlist (Sprint 7B)
Lets a user track specific entities and get their signals prioritized in
the notification feed. Per-user, not global — uses the Watchlist table
(user_id, entity_id).

Endpoints:
  GET    /watchlist                → list the current user's watched entities
  POST   /watchlist/{entity_id}    → add an entity to the watchlist
  DELETE /watchlist/{entity_id}    → remove an entity from the watchlist
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AutocommitSessionLocal, get_db, run_queries
from app.models.entity import Entity
from app.models.user_data import Watchlist
from app.models.metrics import EntityMetric
from app.services.latest_metric import latest_metric
from sqlalchemy import func, literal
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()


@router.get("", summary="List the current user's watchlisted entities")
async def list_watchlist(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Entity, Watchlist.created_at)
        .join(Watchlist, Watchlist.entity_id == Entity.id)
        .where(Watchlist.user_id == user.id)
        .order_by(Watchlist.created_at.desc())
    )
    rows = result.all()

    # Current score = newest snapshot; baseline = newest snapshot at/before the day it was
    # added (falling back to the oldest snapshot), so delta is "change since you started watching".
    ids = [e.id for e, _ in rows]
    current: dict = {}
    series: dict = {}
    if ids:
        lm = latest_metric()
        cur_rows, series_rows = await run_queries(  # independent: run concurrently
            select(lm.entity_id, lm.composite_score, lm.time).where(lm.entity_id.in_(ids)),
            select(EntityMetric.entity_id, EntityMetric.composite_score, EntityMetric.time)
            .where(EntityMetric.entity_id.in_(ids), EntityMetric.composite_score.isnot(None))
            .order_by(EntityMetric.entity_id, EntityMetric.time),
        )
        for eid, sc, t in cur_rows:
            current[eid] = (sc, t)
        for eid, sc, t in series_rows:
            series.setdefault(eid, []).append((t, sc))

    def baseline(eid, since):
        pts = series.get(eid) or []
        if not pts:
            return None
        before = [p for p in pts if since and p[0] <= since]
        return (before[-1] if before else pts[0])[1]

    items = []
    for entity, watched_since in rows:
        cur = current.get(entity.id, (None, None))[0]
        base = baseline(entity.id, watched_since)
        items.append({
            "id": str(entity.id),
            "name": entity.name,
            "category": entity.category,
            "is_international": entity.is_international or False,
            "watched_since": watched_since.isoformat() if watched_since else None,
            "composite_score": round(cur, 1) if cur is not None else None,
            "score_at_watch": round(base, 1) if base is not None else None,
            "score_delta": round(cur - base, 1) if cur is not None and base is not None else None,
        })
    return {
        "watchlist": items,
        "total": len(rows),
    }


@router.post("/{entity_id}", summary="Add an entity to the current user's watchlist", status_code=201)
async def add_to_watchlist(entity_id: str, user: User = Depends(get_current_user)):
    """Idempotent. One INSERT .. SELECT FROM entities (so a missing entity inserts
    nothing) with ON CONFLICT DO NOTHING; keyed strictly by the caller's user id."""
    try:
        uid = UUID(entity_id)
    except (ValueError, AttributeError):
        raise HTTPException(400, "Invalid entity_id format")

    # id/created_at have only Python-side defaults, which from_select would
    # render as ONE shared constant, so they are selected explicitly.
    src = select(literal(user.id, type_=Watchlist.user_id.type), Entity.id,
                 func.gen_random_uuid(), func.now()).where(Entity.id == uid)
    stmt = pg_insert(Watchlist).from_select(["user_id", "entity_id", "id", "created_at"], src, include_defaults=False)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_watchlist_user_entity")
    async with AutocommitSessionLocal() as s:
        result = await s.execute(stmt)
        inserted = (result.rowcount or 0) > 0
        if not inserted:
            on_list = await s.scalar(
                select(Watchlist.entity_id).where(Watchlist.user_id == user.id, Watchlist.entity_id == uid)
            )
            if on_list is None:
                raise HTTPException(404, f"Entity '{entity_id}' not found")
    return {"status": "ok", "entity_id": entity_id, "already_watched": not inserted}


@router.delete("/{entity_id}", summary="Remove an entity from the current user's watchlist")
async def remove_from_watchlist(entity_id: str, user: User = Depends(get_current_user)):
    try:
        uid = UUID(entity_id)
    except (ValueError, AttributeError):
        raise HTTPException(400, "Invalid entity_id format")

    async with AutocommitSessionLocal() as s:
        result = await s.execute(
            delete(Watchlist).where(Watchlist.user_id == user.id, Watchlist.entity_id == uid)
        )
    if result.rowcount == 0:
        raise HTTPException(404, "Entity is not on your watchlist")
    return {"status": "ok", "entity_id": entity_id}

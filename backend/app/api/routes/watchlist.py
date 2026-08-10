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

from app.core.database import get_db
from app.models.entity import Entity
from app.models.user_data import Watchlist
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
    return {
        "watchlist": [
            {
                "id": str(entity.id),
                "name": entity.name,
                "category": entity.category,
                "is_international": entity.is_international or False,
                "watched_since": watched_since.isoformat() if watched_since else None,
            }
            for entity, watched_since in rows
        ],
        "total": len(rows),
    }


@router.post("/{entity_id}", summary="Add an entity to the current user's watchlist", status_code=201)
async def add_to_watchlist(entity_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = await db.scalar(select(Entity).where(Entity.id == uid))
    if entity is None:
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    stmt = pg_insert(Watchlist).values(user_id=user.id, entity_id=uid)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_watchlist_user_entity")
    result = await db.execute(stmt)
    await db.commit()

    return {"status": "ok", "entity_id": entity_id, "already_watched": result.rowcount == 0}


@router.delete("/{entity_id}", summary="Remove an entity from the current user's watchlist")
async def remove_from_watchlist(entity_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    result = await db.execute(
        delete(Watchlist).where(Watchlist.user_id == user.id, Watchlist.entity_id == uid)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Entity is not on your watchlist")
    return {"status": "ok", "entity_id": entity_id}

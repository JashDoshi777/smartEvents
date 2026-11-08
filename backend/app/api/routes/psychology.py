"""
LiveIQ — Psychological Demand Analysis
Real customer-behavior effects computed from actual event history and
social data — see app/services/scoring/psychology_engine.py for the
four factors (overexposure, novelty, FOMO, controversy drag) and their
real data sources. This module never invents a psychological score out
of nothing; every factor either has a real signal backing it or reports
multiplier=1.0 (no adjustment) with an explicit "insufficient data" note.

Endpoint:
  GET /psychology/{entity_id}  → full factor breakdown + combined multiplier
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import ReadOnlySessionLocal, get_db, run_queries
from app.models.entity import Entity
from app.api.deps import get_current_user
from app.models.user import User
from app.services.scoring.psychology_engine import compute_psychology_report

router = APIRouter()


@router.get("/{entity_id}", summary="Real psychological demand-modifier breakdown for an entity")
async def get_psychology_report(
    entity_id: str,
    city: Optional[str] = Query(None, max_length=100, description="Score against this specific city (recommended — most factors are city-scoped)"),
    lead_days: int = Query(60, ge=1, le=730, description="Days from now to the hypothetical event date, for the FOMO/competing-events check"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    target_date = datetime.now(timezone.utc) + timedelta(days=lead_days)
    # Entity lookup and the three factor queries all run concurrently.
    entity_task = run_queries(select(Entity).where(Entity.id == uid))
    report_task = compute_psychology_report(db, uid, city=city, event_date=target_date,
                                            session_factory=ReadOnlySessionLocal)
    (entity_rows,), report = await asyncio.gather(entity_task, report_task)
    if not entity_rows:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    entity = entity_rows[0][0]

    return {
        "entity_id": entity_id,
        "entity_name": entity.name,
        "city": city,
        "combined_multiplier": report.combined_multiplier,
        "interpretation": (
            "Apply this multiplier to a demand/fill-rate estimate (e.g. from /pricing/optimize or "
            "/predict/event-success) — it is NOT a standalone score. 1.0 = no psychological adjustment; "
            "below 1.0 = real factors suppressing demand; above 1.0 = real factors boosting it."
        ),
        "factors": [
            {
                "name": f.name,
                "multiplier": f.multiplier,
                "real_signal": f.real_signal,
                "explanation": f.explanation,
            }
            for f in report.factors
        ],
        "data_coverage_note": report.data_coverage_note,
    }

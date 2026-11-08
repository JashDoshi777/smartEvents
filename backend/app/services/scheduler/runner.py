"""Job wrapper: cross-worker lease lock + job_runs bookkeeping + structured logging + cache invalidation.

run_job(name) never raises: the outcome is returned as a dict and persisted in `job_runs`.
The lease is an atomic upsert on `job_locks` (works through Neon's PgBouncer; session advisory locks do not).
"""
from __future__ import annotations

import asyncio
import os
import socket
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

import structlog
from sqlalchemy import text, update, select

from app.models.job import JobRun

logger = structlog.get_logger()

HOLDER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"

_ACQUIRE_SQL = text(
    """
    INSERT INTO job_locks (name, holder, locked_until) VALUES (:name, :holder, :until)
    ON CONFLICT (name) DO UPDATE SET holder = :holder, locked_until = :until
    WHERE job_locks.locked_until < :now
    RETURNING name
    """
)
_RELEASE_SQL = text("UPDATE job_locks SET locked_until = :now WHERE name = :name AND holder = :holder")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_factory():
    from app.core.database import AsyncSessionLocal
    return AsyncSessionLocal


async def acquire_lock(name: str, ttl_seconds: int, holder: str = HOLDER, session_factory=None) -> bool:
    """True if this caller now holds the lease (previous lease expired / never existed)."""
    sf = session_factory or _session_factory()
    now = _now()
    async with sf() as s:
        row = (await s.execute(_ACQUIRE_SQL, {"name": name, "holder": holder, "until": now + timedelta(seconds=ttl_seconds), "now": now})).first()
        await s.commit()
    return row is not None


async def release_lock(name: str, holder: str = HOLDER, session_factory=None) -> None:
    sf = session_factory or _session_factory()
    async with sf() as s:
        await s.execute(_RELEASE_SQL, {"name": name, "holder": holder, "now": _now()})
        await s.commit()


def _rows(result: Any) -> Optional[int]:
    """Jobs return an int, or a dict with a 'rows' key (+ extra detail), or None."""
    if isinstance(result, bool):
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, dict) and isinstance(result.get("rows"), int):
        return result["rows"]
    return None


async def run_job(name: str, func: Callable[[], Awaitable[Any]], *, lease_seconds: int = 3600,
                  timeout: Optional[float] = None, trigger: str = "schedule", session_factory=None,
                  invalidate_cache: bool = True) -> Dict[str, Any]:
    """Run `func` under the lease lock, recording a job_runs row. Never raises."""
    sf = session_factory or _session_factory()
    log = logger.bind(job=name, trigger=trigger)
    try:
        got = await acquire_lock(name, lease_seconds, session_factory=sf)
    except Exception as exc:  # DB down: do not crash the scheduler
        log.error("job lock failed", error=str(exc)[:300])
        return {"job": name, "status": "error", "error": f"lock: {str(exc)[:300]}"}
    if not got:
        log.info("job skipped: another worker holds the lease")
        return {"job": name, "status": "skipped", "reason": "lease held by another runner"}

    run_id = uuid.uuid4()
    started = _now()
    outcome: Dict[str, Any] = {"job": name, "run_id": str(run_id), "status": "error"}
    try:
        async with sf() as s:
            s.add(JobRun(id=run_id, job_name=name, started_at=started, status="running", trigger=trigger))
            await s.commit()
        log.info("job started", run_id=str(run_id))
        status, rows, err, detail = "success", None, None, None
        try:
            result = await (asyncio.wait_for(func(), timeout) if timeout else func())
            rows = _rows(result)
            detail = result if isinstance(result, dict) else None
            if isinstance(result, dict) and str(result.get("status", "")).startswith("partial"):
                status = "partial"
        except asyncio.CancelledError:
            status, err = "error", "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - recorded, never propagated
            status, err = "error", f"{type(exc).__name__}: {str(exc)[:500]}"
            log.error("job failed", error=err, tb=traceback.format_exc()[-800:])
        finally:
            try:
                async with sf() as s:
                    await s.execute(update(JobRun).where(JobRun.id == run_id).values(
                        finished_at=_now(), status=status, rows_affected=rows, error=err, detail=_jsonable(detail)))
                    await s.commit()
            except Exception as exc:  # noqa: BLE001
                log.error("job_runs update failed", error=str(exc)[:300])
        outcome.update(status=status, rows_affected=rows, error=err)
        if status in ("success", "partial") and invalidate_cache:
            try:
                from app.core.response_cache import invalidate_all
                outcome["cache_cleared"] = invalidate_all()
            except Exception as exc:  # noqa: BLE001
                log.warning("cache invalidation failed", error=str(exc)[:200])
        log.info("job finished", status=status, rows=rows)
    finally:
        try:
            await release_lock(name, session_factory=sf)
        except Exception as exc:  # noqa: BLE001
            logger.warning("job lock release failed", job=name, error=str(exc)[:200])
    return outcome


def _jsonable(d: Any) -> Any:
    import json
    if d is None:
        return None
    try:
        return json.loads(json.dumps(d, default=str))
    except Exception:  # noqa: BLE001
        return None


async def mark_abandoned_runs(session_factory=None, older_than_minutes: int = 180) -> int:
    """Rows left 'running' by a crashed process (older than any lease) are closed as error."""
    sf = session_factory or _session_factory()
    cutoff = _now() - timedelta(minutes=older_than_minutes)
    async with sf() as s:
        res = await s.execute(update(JobRun).where(JobRun.status == "running", JobRun.started_at < cutoff)
                              .values(status="error", finished_at=_now(), error="abandoned (process stopped mid-run)"))
        await s.commit()
        return res.rowcount or 0


async def recent_runs(limit: int = 50, session_factory=None) -> list[dict]:
    sf = session_factory or _session_factory()
    async with sf() as s:
        rows = (await s.execute(select(JobRun).order_by(JobRun.started_at.desc()).limit(limit))).scalars().all()
    return [serialize_run(r) for r in rows]


def serialize_run(r: JobRun) -> dict:
    return {
        "id": str(r.id), "job": r.job_name, "status": r.status, "trigger": r.trigger,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "rows_affected": r.rows_affected, "error": r.error, "detail": r.detail,
    }

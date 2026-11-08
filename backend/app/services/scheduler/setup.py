"""APScheduler wiring. Disabled by SCHEDULER_ENABLED=false and automatically under pytest."""
from __future__ import annotations

import os
import sys
from typing import Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.scheduler.jobs import JOBS
from app.services.scheduler.runner import run_job, mark_abandoned_runs

logger = structlog.get_logger()
TZ = "Asia/Kolkata"
_scheduler: Optional[AsyncIOScheduler] = None


def scheduler_enabled() -> bool:
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        from app.core.config import settings
        flag = settings.SCHEDULER_ENABLED
    except Exception:  # noqa: BLE001
        flag = True
    env = os.environ.get("SCHEDULER_ENABLED")
    if env is not None:
        flag = env.strip().lower() not in ("0", "false", "no", "off")
    return bool(flag)


async def execute(name: str, trigger: str = "schedule") -> dict:
    spec = JOBS[name]
    return await run_job(name, spec.func, lease_seconds=spec.lease_seconds, timeout=spec.timeout, trigger=trigger)


def build_scheduler() -> AsyncIOScheduler:
    """Create (not start) the scheduler with every job registered."""
    sched = AsyncIOScheduler(timezone=TZ)
    for spec in JOBS.values():
        sched.add_job(
            execute, CronTrigger(timezone=TZ, jitter=spec.jitter, **spec.cron), args=[spec.name],
            id=spec.name, name=spec.name, max_instances=1, coalesce=True,
            misfire_grace_time=3600, replace_existing=True)
    return sched


async def start_scheduler() -> Optional[AsyncIOScheduler]:
    global _scheduler
    if not scheduler_enabled():
        logger.info("scheduler disabled")
        return None
    try:
        n = await mark_abandoned_runs()
        if n:
            logger.warning("closed abandoned job runs", count=n)
    except Exception as exc:  # noqa: BLE001
        logger.warning("abandoned-run sweep failed", error=str(exc)[:200])
    _scheduler = build_scheduler()
    _scheduler.start()
    logger.info("scheduler started", jobs=[j.id for j in _scheduler.get_jobs()])
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_summary() -> dict:
    if _scheduler is None:
        return {"enabled": False}
    return {"enabled": True, "jobs": {j.id: (j.next_run_time.isoformat() if j.next_run_time else None) for j in _scheduler.get_jobs()}}

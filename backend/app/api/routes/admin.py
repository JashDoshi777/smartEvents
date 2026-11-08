"""Admin / operations endpoints.

  POST /admin/cache/clear        executive only - empties the in-memory response cache
  GET  /admin/jobs               executive/analyst - scheduler jobs, schedules, recent job_runs (uncached)
  POST /admin/jobs/{name}/run    executive only - trigger a job now (runs in the background, lease-locked)
"""
import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_roles
from app.core.response_cache import cache_stats, invalidate_all
from app.models.user import User, UserRole

router = APIRouter()
logger = structlog.get_logger()


@router.post("/cache/clear", summary="Clear the API response cache (executive only)")
async def clear_cache(user: User = Depends(require_roles(UserRole.EXECUTIVE))):
    cleared = invalidate_all()
    logger.info("response cache cleared", by=str(user.id), entries=cleared)
    return {"status": "ok", "cleared_entries": cleared, "cache": cache_stats()}


_BG: set = set()   # keeps references to manually triggered job tasks


@router.get("/jobs", summary="Scheduler jobs + recent runs (executive/analyst)")
async def list_jobs(limit: int = Query(30, ge=1, le=200),
                    user: User = Depends(require_roles(UserRole.EXECUTIVE, UserRole.ANALYST))):
    from app.services.scheduler.jobs import JOBS
    from app.services.scheduler.runner import recent_runs
    from app.services.scheduler.setup import scheduler_summary, scheduler_enabled
    runs = await recent_runs(limit)
    last: dict = {}
    for r in runs:  # newest first
        last.setdefault(r["job"], r)
    summary = scheduler_summary()
    return {
        "scheduler": {"enabled_in_this_process": summary.get("enabled", False), "env_enabled": scheduler_enabled()},
        "jobs": [
            {"name": j.name, "description": j.description, "cron_ist": j.cron,
             "next_run": (summary.get("jobs") or {}).get(j.name), "last_run": last.get(j.name)}
            for j in JOBS.values()
        ],
        "runs": runs,
    }


@router.post("/jobs/{name}/run", status_code=202, summary="Run a scheduler job now (executive only)")
async def run_job_now(name: str, user: User = Depends(require_roles(UserRole.EXECUTIVE))):
    from app.services.scheduler.jobs import JOBS
    from app.services.scheduler.setup import execute
    if name not in JOBS:
        raise HTTPException(404, f"Unknown job '{name}'. Known: {sorted(JOBS)}")
    task = asyncio.create_task(execute(name, trigger="manual"))
    _BG.add(task)
    task.add_done_callback(_BG.discard)
    logger.info("job triggered manually", job=name, by=str(user.id))
    return {"status": "accepted", "job": name, "note": "runs in the background under the job lease; see GET /admin/jobs"}

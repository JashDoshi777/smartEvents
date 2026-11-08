"""Scheduler: config, lease locking, job wrapper (work is mocked; SQLite in-memory stands in for Postgres)."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.models.job import JobLock, JobRun
from app.services.scheduler import runner
from app.services.scheduler.jobs import JOBS, eval_counts
from app.services.scheduler.setup import build_scheduler, scheduler_enabled


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def _uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@pytest.fixture
async def sf():
    eng = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with eng.begin() as c:
        await c.run_sync(lambda conn: (JobLock.__table__.create(conn), JobRun.__table__.create(conn)))
    yield async_sessionmaker(eng, expire_on_commit=False)
    await eng.dispose()


def test_disabled_under_pytest():
    assert scheduler_enabled() is False


def test_build_scheduler_registers_all_jobs_non_overlapping():
    sched = build_scheduler()
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == set(JOBS)
    for j in jobs.values():
        assert j.max_instances == 1
        assert j.coalesce is True
        assert j.trigger.jitter and j.trigger.jitter > 0
    assert {"entity_metrics", "free_signals", "district_events", "social_listening", "wikidata_enrichment", "news_backfill", "attention_refresh"} <= set(jobs)
    assert JOBS["attention_refresh"].cron["day_of_week"] == "mon"


def test_eval_counts_parser():
    assert eval_counts("{'created': 3, 'updated': 4, 'skipped': 1}") == {"created": 3, "updated": 4, "skipped": 1}


async def test_lock_is_exclusive_and_expires(sf):
    assert await runner.acquire_lock("j", 60, holder="a", session_factory=sf) is True
    assert await runner.acquire_lock("j", 60, holder="b", session_factory=sf) is False
    await runner.release_lock("j", holder="a", session_factory=sf)
    assert await runner.acquire_lock("j", 60, holder="b", session_factory=sf) is True
    # an expired lease can be stolen (crashed holder)
    async with sf() as s:
        await s.execute(text("UPDATE job_locks SET locked_until=:t"), {"t": datetime.now(timezone.utc) - timedelta(seconds=5)})
        await s.commit()
    assert await runner.acquire_lock("j", 60, holder="c", session_factory=sf) is True


async def test_run_job_success_records_row_and_clears_cache(sf):
    async def work():
        return {"rows": 7, "status": "complete"}

    with patch("app.core.response_cache.invalidate_all", return_value=3) as inv:
        out = await runner.run_job("t", work, session_factory=sf)
    assert out["status"] == "success" and out["rows_affected"] == 7 and out["cache_cleared"] == 3
    inv.assert_called_once()
    async with sf() as s:
        run = (await s.execute(select(JobRun))).scalar_one()
    assert run.status == "success" and run.rows_affected == 7 and run.finished_at is not None
    # lease released: can run again immediately
    assert (await runner.run_job("t", work, session_factory=sf))["status"] == "success"


async def test_run_job_error_is_captured_not_raised(sf):
    async def boom():
        raise ValueError("kaput")

    with patch("app.core.response_cache.invalidate_all") as inv:
        out = await runner.run_job("t", boom, session_factory=sf)
    assert out["status"] == "error" and "kaput" in out["error"]
    inv.assert_not_called()  # no invalidation after a failed job
    async with sf() as s:
        run = (await s.execute(select(JobRun))).scalar_one()
    assert run.status == "error" and "kaput" in run.error


async def test_run_job_skips_when_lease_held(sf):
    await runner.acquire_lock("t", 600, holder="other", session_factory=sf)
    called = False

    async def work():
        nonlocal called
        called = True

    out = await runner.run_job("t", work, session_factory=sf)
    assert out["status"] == "skipped" and called is False
    async with sf() as s:
        assert (await s.execute(select(JobRun))).first() is None


async def test_run_job_timeout_recorded(sf):
    async def slow():
        await asyncio.sleep(5)

    out = await runner.run_job("t", slow, session_factory=sf, timeout=0.05)
    assert out["status"] == "error"


async def test_abandoned_runs_closed(sf):
    async with sf() as s:
        s.add(JobRun(job_name="x", started_at=datetime.now(timezone.utc) - timedelta(hours=9), status="running"))
        await s.commit()
    assert await runner.mark_abandoned_runs(session_factory=sf) == 1

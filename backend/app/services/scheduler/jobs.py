"""Job registry. Each job is a plain async function (no Celery) returning rows affected or {"rows": n, ...}.

Script-backed jobs (free signals, District sync, Wikidata enrichment) run the existing, tested CLI scripts in a
subprocess: they use blocking HTTP/sync DB code and Playwright, which must not run on the API event loop.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

import structlog

logger = structlog.get_logger()

BACKEND_DIR = Path(__file__).resolve().parents[3]


async def run_script(args: list[str], timeout: float, env_extra: Optional[Dict[str, str]] = None) -> tuple[int, str]:
    env = {**os.environ, "PYTHONUNBUFFERED": "1", **(env_extra or {})}
    proc = await asyncio.create_subprocess_exec(
        sys.executable, *args, cwd=str(BACKEND_DIR), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    text = out.decode("utf-8", "replace")
    return proc.returncode or 0, text[-4000:]


def _check(code: int, out: str, what: str) -> None:
    if code != 0:
        raise RuntimeError(f"{what} exited {code}: {out[-300:]}")


# ── job bodies ────────────────────────────────────────────────────────────────

async def job_entity_metrics() -> Dict[str, Any]:
    from app.workers.entity_metrics import collect_entity_metrics_batch
    return await collect_entity_metrics_batch(limit=int(os.environ.get("JOB_ENTITY_METRICS_BATCH", "60")))


async def job_free_signals() -> Dict[str, Any]:
    code, out = await run_script(["scripts/collect_free_signals.py", "--steps", "wiki,youtube"], timeout=3000)
    _check(code, out, "collect_free_signals")
    m = re.search(r"entities to write:\s*(\d+)", out)
    return {"rows": int(m.group(1)) if m else None, "tail": out[-300:]}


async def job_district_events() -> Dict[str, Any]:
    code, out = await run_script(["scripts/sync_district_events.py"], timeout=3400)
    _check(code, out, "sync_district_events")
    m = re.search(r"TOTAL\s*(\{.*\})", out)
    rows = None
    if m:
        try:
            d = eval_counts(m.group(1))
            rows = sum(v for k, v in d.items() if k in ("created", "inserted", "updated", "new"))
        except Exception:  # noqa: BLE001
            pass
    return {"rows": rows, "tail": out[-300:]}


def eval_counts(s: str) -> Dict[str, int]:
    """Parse a printed {'k': 1, ...} dict without eval."""
    return {k: int(v) for k, v in re.findall(r"'([^']+)':\s*(-?\d+)", s)}


async def job_social_listening() -> Dict[str, Any]:
    from app.workers.social_listening import _collect_all_social
    r = await _collect_all_social(limit=int(os.environ.get("JOB_SOCIAL_BATCH", "10")))
    return {"rows": r.get("processed", 0), **{k: v for k, v in r.items() if k != "processed"}}


async def job_wikidata_enrichment() -> Dict[str, Any]:
    code, out = await run_script(["scripts/enrich_entities_wikidata.py", "--new-only"], timeout=3000)
    _check(code, out, "enrich_entities_wikidata")
    m = re.search(r"written\s+(\d+)", out)
    return {"rows": int(m.group(1)) if m else 0, "tail": out[-300:]}


async def job_news_backfill() -> Dict[str, Any]:
    from app.services.ingestion.news_free_client import backfill_news_mentions
    return await backfill_news_mentions(limit=int(os.environ.get("JOB_NEWS_BATCH", "30")))


async def job_attention_refresh() -> Dict[str, Any]:
    """Weekly: upsert the last 2 complete ISO weeks of Wikipedia pageviews into entity_attention_weekly and refresh
    wikipedia_views_30d/_7d. Momentum (app/services/momentum.py) is computed on read, so nothing else to refresh."""
    code, out = await run_script(["scripts/backfill_attention.py", "--weeks", "2"], timeout=3300)
    _check(code, out, "backfill_attention")
    m = re.search(r"weekly rows upserted:\s*(\d+)", out)
    return {"rows": int(m.group(1)) if m else 0, "tail": out[-300:]}


@dataclass(frozen=True)
class JobSpec:
    name: str
    func: Callable[[], Awaitable[Any]]
    description: str
    cron: Dict[str, Any]          # APScheduler CronTrigger kwargs (Asia/Kolkata)
    jitter: int = 300             # seconds of random start jitter
    timeout: float = 3500
    lease_seconds: int = 3700


JOBS: Dict[str, JobSpec] = {j.name: j for j in [
    JobSpec("entity_metrics", job_entity_metrics, "Last.fm / YouTube / Google Trends / news for the 60 stalest entities (rotates; builds forecast history)", {"hour": 2, "minute": 30}),
    JobSpec("free_signals", job_free_signals, "Wikipedia pageviews + YouTube subscribers refresh", {"hour": 4, "minute": 0}),
    JobSpec("district_events", job_district_events, "District.in listings sync for supported cities", {"hour": 5, "minute": 0}, timeout=3400),
    JobSpec("social_listening", job_social_listening, "Rotating social-listening sweep (10 stalest entities)", {"minute": 20}, jitter=120, timeout=1500, lease_seconds=1600),
    JobSpec("wikidata_enrichment", job_wikidata_enrichment, "Wikidata/Wikipedia enrichment of newly added entities", {"day_of_week": "sun", "hour": 3, "minute": 0}),
    JobSpec("news_backfill", job_news_backfill, "Keyless news mentions (GDELT / Google News) for entities with NULL news_mentions_7d", {"hour": 3, "minute": 30}, timeout=3000, lease_seconds=3200),
    JobSpec("attention_refresh", job_attention_refresh, "Weekly Wikipedia pageview history (last 2 ISO weeks) -> entity_attention_weekly; momentum derives from it", {"day_of_week": "mon", "hour": 6, "minute": 0}, timeout=3400, lease_seconds=3500),
]}

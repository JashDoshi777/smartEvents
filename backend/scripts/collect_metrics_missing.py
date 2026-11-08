"""
Phase C (metrics) — collect REAL metrics (Last.fm / YouTube / Google Trends / NewsAPI) for active entities
that have no entity_metrics row yet, using the production collector `_process_single_entity`.

* small batches, semaphore of 3, pause between batches (NewsAPI free tier + pytrends rate limits)
* a failing source simply leaves that signal NULL and lowers data_completeness (never filled in)
* resumable/idempotent: only entities with zero metric rows are selected, so re-running continues
* --retry-incomplete re-collects entities whose latest row has data_completeness < 1 (e.g. news skipped on 429)

Usage: python scripts/collect_metrics_missing.py [--limit N] [--batch 15] [--pause 20] [--retry-incomplete]
"""
import argparse
import asyncio
import sys
import time

sys.path.insert(0, ".")
from sqlalchemy import text

from app.core.database import AsyncSessionLocal


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=15)
    ap.add_argument("--pause", type=float, default=20)
    ap.add_argument("--retry-incomplete", action="store_true")
    a = ap.parse_args()
    import app.workers.entity_metrics as em
    from app.workers.entity_metrics import _process_single_entity

    # NewsAPI free tier rate-limits quickly: after the first 429/failure, skip news for the rest of the run
    # (news fields stay NULL, data_completeness reflects it; use --retry-incomplete later).
    news_state = {"blocked": False, "skipped": 0}
    orig_news = em._fetch_news_metrics

    async def news_guard(name):
        if news_state["blocked"]:
            news_state["skipped"] += 1
            raise RuntimeError("news skipped (NewsAPI rate-limited earlier in this run)")
        try:
            return await orig_news(name)
        except Exception as exc:  # noqa: BLE001
            if "429" in str(exc) or "Too Many" in str(exc) or "retries" in str(exc).lower():
                news_state["blocked"] = True
                print("NewsAPI rate-limited -> skipping news for the rest of this run", flush=True)
            raise

    em._fetch_news_metrics = news_guard

    if a.retry_incomplete:
        sql = """select e.id,e.name,e.external_ids,e.entity_type,e.category from entities e
                 join lateral (select data_completeness from entity_metrics m where m.entity_id=e.id order by time desc limit 1) m on true
                 where e.status='active' and coalesce(m.data_completeness,0) < 1 order by e.name limit :n"""
    else:
        sql = """select e.id,e.name,e.external_ids,e.entity_type,e.category from entities e
                 where e.status='active' and not exists (select 1 from entity_metrics m where m.entity_id=e.id)
                 order by (e.data_provenance->>'sitelinks')::int desc nulls last, e.name limit :n"""
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text(sql), {"n": a.limit})).all()
    ents = [{"id": r[0], "name": r[1], "external_ids": r[2] or {}, "entity_type": r[3], "category": r[4]} for r in rows]
    print(f"entities to collect: {len(ents)}", flush=True)
    sem = asyncio.Semaphore(3)
    ok = fail = 0

    async def one(e):
        nonlocal ok, fail
        async with sem:
            try:
                m = await _process_single_entity(e)
                ok += 1
                return m
            except Exception as exc:  # one bad API call must not abort the batch
                fail += 1
                print("FAILED", e["name"], str(exc)[:120], flush=True)

    for i in range(0, len(ents), a.batch):
        t = time.time()
        await asyncio.gather(*[one(e) for e in ents[i:i + a.batch]])
        print(f"batch {i // a.batch + 1}: done {ok} failed {fail} ({time.time() - t:.0f}s)", flush=True)
        await asyncio.sleep(a.pause)
    print(f"collected {ok}, failed {fail}")


if __name__ == "__main__":
    asyncio.run(main())

"""Re-run keyless news counts with the title filter (app/services/news_filter.py) for
 (a) active entities whose name is a generic single word, and (b) the top N Indian entities by latest composite score.
Matches the full name OR any alias (entities.name_aliases). Overwrites news_mentions_7d / news_confidence / news_sample_titles on the entity's NEWEST entity_metrics row
(NULL when 'ambiguous_skipped'; the old unfiltered value is kept in signal_provenance.news_mentions_7d_prev).
Resumable via scratchpad json. Usage: python scripts/rerun_news_filtered.py [--top 150] [--limit N]"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, ".")
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.ingestion.news_free_client import fetch_news_mentions
from app.services.news_filter import disambiguator_of, is_generic_name

SCRATCH = "/private/tmp/claude-501/-Users-jash-doshi-zomato-com-Desktop-event/9552e9da-2773-47bc-b57e-03c883fcc8dc/scratchpad/news_rerun_alias3.json"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=150)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--zero-only", action="store_true", help="only rows whose strict count is currently 0/NULL (alias re-run)")
    a = ap.parse_args()
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT e.id, e.name, e.entity_type, e.category, COALESCE(e.is_international,false) AS intl,
                   e.external_ids->>'wikipedia_title' AS wt, e.primary_market, e.name_aliases AS al, m.time, m.news_mentions_7d AS old, m.composite_score
            FROM entities e JOIN LATERAL (SELECT time, news_mentions_7d, composite_score FROM entity_metrics WHERE entity_id=e.id
                 ORDER BY time DESC LIMIT 1) m ON true WHERE e.status='active'"""))).mappings().all()
    india = sorted([r for r in rows if r["primary_market"] == "India" and not r["intl"]], key=lambda r: -(r["composite_score"] or 0))
    pick = {r["id"]: r for r in india[: a.top]}
    for r in rows:
        if is_generic_name(r["name"]):
            pick[r["id"]] = r
    if a.zero_only:
        pick = {k: v for k, v in pick.items() if not v["old"]}
    todo = list(pick.values())[: a.limit] if a.limit else list(pick.values())
    done = json.load(open(SCRATCH)) if os.path.exists(SCRATCH) else {}
    print("to process", len(todo), "already", len(done), flush=True)
    for i, r in enumerate(todo):
        if str(r["id"]) in done:
            continue
        res = await fetch_news_mentions(r["name"], r["entity_type"], r["category"], r["intl"], disambiguator=disambiguator_of(r["wt"]), aliases=r["al"] or [])
        if res is None:
            print("no source answered:", r["name"], flush=True)
            continue
        prov = json.dumps({"news_mentions_7d": res.provenance(), "news_mentions_7d_prev": {"value": r["old"], "note": "unfiltered, replaced"}})
        async with AsyncSessionLocal() as s:
            await s.execute(text("""UPDATE entity_metrics SET news_mentions_7d=:n, news_confidence=:c, news_sample_titles=CAST(:t AS jsonb),
                    signal_provenance = COALESCE(signal_provenance,'{}'::jsonb) || CAST(:p AS jsonb)
                    WHERE entity_id=:e AND time=:tm"""), {"n": res.count, "c": res.confidence, "t": json.dumps(res.sample_titles), "p": prov, "e": r["id"], "tm": r["time"]})
            await s.commit()
        done[str(r["id"])] = {"name": r["name"], "old": r["old"], "new": res.count, "conf": res.confidence}
        json.dump(done, open(SCRATCH, "w"))
        if i % 10 == 0:
            print(i, r["name"], r["old"], "->", res.count, res.confidence, flush=True)

asyncio.run(main())

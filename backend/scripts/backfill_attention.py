"""Backfill / refresh entity_attention_weekly from Wikimedia daily user pageviews (en + hi Wikipedia).

  python scripts/backfill_attention.py [--weeks 26] [--limit N] [--dry-run] [--no-metrics]

* titles come from Wikidata sitelinks (entities.external_ids.wikidata_qid; cached in scratchpad wd_facts.json)
* per-article daily pageviews are cached per (project,title,fetch-date) so the script is resumable; ~5 req/s max
* only complete ISO weeks are stored; upsert on (entity_id, week_start) -> idempotent
* also refreshes wikipedia_views_30d/_7d on each entity's newest entity_metrics row (provenance noted)
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
import requests
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.attention import aggregate_weekly, daily_from_items, last_complete_week_start, trailing_sum, week_range
import wikidata_ids_cache

PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{proj}/all-access/user/{title}/daily/{s}/{e}"
SRC = "wikimedia_pageviews:user:all-access:daily->iso_week"
_last = [0.0]


def fetch_daily(proj, title, start, end, today):
    """-> dict[date,int] | None (404/no data or persistent error). Cached per fetch day."""
    key = hashlib.sha1(f"{proj}|{title}|{start}|{end}".encode()).hexdigest()
    cp = os.path.join(_wd.CACHE_DIR, "pv_" + today.isoformat() + "_" + key + ".json")
    if os.path.exists(cp):
        v = json.load(open(cp))
        return None if v is None else {date.fromisoformat(k): n for k, n in v.items()}
    url = PV.format(proj=proj, title=quote(title.replace(" ", "_"), safe=""), s=start.strftime("%Y%m%d"), e=end.strftime("%Y%m%d"))
    result, ok = None, False
    for i in range(5):
        w = 0.2 - (time.time() - _last[0])
        if w > 0:
            time.sleep(w)
        _last[0] = time.time()
        try:
            r = _wd.S.get(url, timeout=30)
        except requests.RequestException:
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 200:
            result, ok = daily_from_items(r.json().get("items", [])), True
            break
        if r.status_code == 404:
            ok = True            # no data in range
            break
        time.sleep(int(r.headers.get("Retry-After", 5 * (i + 1))) if r.status_code in (429, 503) else 2 * (i + 1))
    if ok:
        json.dump(None if result is None else {d.isoformat(): n for d, n in result.items()}, open(cp, "w"))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=26)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-metrics", action="store_true")
    a = ap.parse_args()
    today = datetime.now(timezone.utc).date()
    weeks = week_range(today, a.weeks)
    start, end = weeks[0], weeks[-1] + timedelta(days=6)
    # 30-day trailing window may begin before `start` never (26 weeks > 30 days) but end may be past `end`
    fetch_end = today - timedelta(days=1)
    fetch_start = min(start, today - timedelta(days=31))   # incremental runs still need a full trailing 30d for the metrics refresh

    eng = create_engine(settings.POSTGRES_SYNC_URL, pool_pre_ping=True, connect_args={"connect_timeout": 20})
    with eng.connect() as c:
        ents = c.execute(text("SELECT id, name, external_ids->>'wikidata_qid' AS qid FROM entities WHERE status='active' ORDER BY name")).mappings().all()
    ents = ents[: a.limit] if a.limit else ents
    no_qid = [e for e in ents if not e["qid"]]
    facts = wikidata_ids_cache.fetch_facts([e["qid"] for e in ents if e["qid"]])

    weekly_rows, m_rows = [], []
    no_link = 0
    now = datetime.now(timezone.utc)
    for n, e in enumerate(ents):
        f = facts.get(e["qid"]) if e["qid"] else None
        if not f or f.get("missing") or not (f.get("en") or f.get("hi")):
            no_link += 1
            continue
        en = fetch_daily("en.wikipedia", f["en"], fetch_start, fetch_end, today) if f.get("en") else None
        hi = fetch_daily("hi.wikipedia", f["hi"], fetch_start, fetch_end, today) if f.get("hi") else None
        if en is None and hi is None:
            continue                      # sitelink exists but no pageview data came back: store nothing (NULL)
        wk_en = aggregate_weekly(en, today, a.weeks) if en is not None else None
        wk_hi = aggregate_weekly(hi, today, a.weeks) if hi is not None else None
        for w in weeks:
            ve, vh = (wk_en or {}).get(w), (wk_hi or {}).get(w)
            weekly_rows.append((e["id"], w, ve, vh, (ve or 0) + (vh or 0)))
        d_all = {}
        for dd in (en, hi):
            for k, v in (dd or {}).items():
                d_all[k] = d_all.get(k, 0) + v
        m_rows.append((e["id"], trailing_sum(d_all, today, 30), trailing_sum(d_all, today, 7)))
        if n % 50 == 0:
            print(f"{n}/{len(ents)} fetched", flush=True)

    print(f"entities={len(ents)} no_qid={len(no_qid)} no_en_hi_sitelink={no_link - len(no_qid)} with_history={len(m_rows)}")
    if a.dry_run:
        return
    with eng.begin() as c:
        for i in range(0, len(weekly_rows), 3000):
            ch = weekly_rows[i:i + 3000]
            c.execute(text("""
                INSERT INTO entity_attention_weekly (entity_id, week_start, wikipedia_views_en, wikipedia_views_hi, total, source, retrieved_at)
                SELECT * FROM unnest(CAST(:ids AS uuid[]), CAST(:ws AS date[]), CAST(:en AS bigint[]), CAST(:hi AS bigint[]), CAST(:tot AS bigint[]))
                       AS t(entity_id, week_start, en, hi, total), (SELECT CAST(:src AS text) AS src, CAST(:ts AS timestamptz) AS ts) k
                ON CONFLICT (entity_id, week_start) DO UPDATE SET wikipedia_views_en = EXCLUDED.wikipedia_views_en,
                    wikipedia_views_hi = EXCLUDED.wikipedia_views_hi, total = EXCLUDED.total,
                    source = EXCLUDED.source, retrieved_at = EXCLUDED.retrieved_at"""),
                {"ids": [str(r[0]) for r in ch], "ws": [r[1] for r in ch], "en": [r[2] for r in ch], "hi": [r[3] for r in ch],
                 "tot": [r[4] for r in ch], "src": SRC, "ts": now})
        print("weekly rows upserted:", len(weekly_rows))
        if not a.no_metrics and m_rows:
            prov = json.dumps({"wikipedia_views_30d": {"source": "wikimedia_pageviews", "retrieved": today.isoformat(),
                                                       "note": "en+hi user all-access, trailing complete UTC days"},
                               "wikipedia_views_7d": {"source": "wikimedia_pageviews", "retrieved": today.isoformat()}})
            r = c.execute(text("""
                UPDATE entity_metrics m SET wikipedia_views_30d = t.v30, wikipedia_views_7d = t.v7,
                       signal_provenance = COALESCE(m.signal_provenance, '{}'::jsonb) || CAST(:p AS jsonb)
                FROM unnest(CAST(:ids AS uuid[]), CAST(:v30 AS bigint[]), CAST(:v7 AS bigint[])) AS t(eid, v30, v7)
                WHERE m.entity_id = t.eid AND m.time = (SELECT max(time) FROM entity_metrics x WHERE x.entity_id = t.eid)"""),
                {"ids": [str(r[0]) for r in m_rows], "v30": [r[1] for r in m_rows], "v7": [r[2] for r in m_rows], "p": prov})
            print("entity_metrics rows refreshed:", r.rowcount)


if __name__ == "__main__":
    main()

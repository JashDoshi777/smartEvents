"""Anchor-normalised Google Trends for active entities (see app/services/google_trends_relative.py).

  python scripts/collect_google_trends_relative.py [--limit N] [--write] [--delay 8]

Per request: anchor topic + up to 4 entities (topic id from Wikidata P646 when present, else plain name ONLY if safe).
Resumable: results accumulate in $SCRATCH/gt_relative_results.json; entities already there are skipped.
429/blocked -> exponential backoff (60s..), stop after 5 consecutive failures (rerun later).
--write updates each entity's NEWEST entity_metrics row (google_trend_relative/_topic/_basis + provenance);
legacy google_trend_score is never touched.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services import google_trends_relative as G
import wikidata_ids_cache

RES = os.path.join(_wd.CACHE_DIR, "gt_relative_results.json")


def load_res():
    try:
        return json.load(open(RES))
    except Exception:  # noqa: BLE001
        return {}


def fetch_group(keys):
    from pytrends.request import TrendReq
    pt = TrendReq(hl="en-IN", tz=330, timeout=(10, 25))
    pt.build_payload([G.ANCHOR_TOPIC] + keys, geo=G.GEO, timeframe=G.TIMEFRAME)
    df = pt.interest_over_time()
    return {} if df.empty else {c: df[c].tolist() for c in df.columns if c != "isPartial"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--delay", type=float, default=8.0)
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL, pool_pre_ping=True, connect_args={"connect_timeout": 20})
    with eng.connect() as c:
        ents = c.execute(text("""SELECT id, name, entity_type, external_ids->>'wikidata_qid' AS qid,
                                 external_ids->>'wikipedia_title' AS wt, external_ids->>'google_kg_id' AS kg
                                 FROM entities WHERE status='active' ORDER BY name""")).mappings().all()
    facts = wikidata_ids_cache.fetch_facts([e["qid"] for e in ents if e["qid"]])
    res = load_res()
    plan = {}
    for e in ents:
        f = facts.get(e["qid"]) or {}
        topic = e["kg"] or (f.get("p646") or [None])[0]
        if topic:
            plan[str(e["id"])] = ("topic", topic, e["name"])
        elif G.term_allowed(e["name"], e["entity_type"], e["wt"], f.get("p31") or []):
            plan[str(e["id"])] = ("term", e["name"], e["name"])
        else:
            res.setdefault(str(e["id"]), {"basis": "none", "key": None, "relative": None})
    todo = [(eid, b, k) for eid, (b, k, _n) in plan.items() if eid not in res]
    todo = todo[: a.limit] if a.limit else todo
    print(f"entities={len(ents)} topic={sum(1 for v in plan.values() if v[0]=='topic')} term={sum(1 for v in plan.values() if v[0]=='term')} none={len(ents)-len(plan)} todo={len(todo)}", flush=True)
    fails = 0
    for eid, b, k in [t for t in todo if t[2] == G.ANCHOR_TOPIC]:     # the anchor itself: ratio is 1.0 by definition
        res[eid] = {"basis": b, "key": k, "relative": 1.0, "recent_delta_pct": None, "entity_mean": None, "anchor_mean": None}
    todo = [t for t in todo if t[2] != G.ANCHOR_TOPIC]
    for batch in G.make_batches(todo, 4):
        keys = [k for _e, _b, k in batch]
        if len(set(keys)) != len(keys):
            continue
        for attempt in range(5):
            try:
                series = fetch_group(keys)
                fails = 0
                break
            except Exception as exc:  # noqa: BLE001
                fails += 1
                wait = 60 * (2 ** attempt)
                print(f"pytrends error {type(exc).__name__} {str(exc)[:80]}; sleeping {wait}s", flush=True)
                if fails >= 5:
                    json.dump(res, open(RES, "w"))
                    print("too many consecutive failures; stopping (resume later)")
                    return
                time.sleep(wait)
        else:
            continue
        anchor = series.get(G.ANCHOR_TOPIC, [])
        for eid, b, k in batch:
            s = G.summarize(series.get(k, []), anchor) if k in series else {"relative": None}
            res[eid] = {"basis": b, "key": k, **s}
        json.dump(res, open(RES, "w"))
        print(f"done {len(res)} results", flush=True)
        time.sleep(a.delay)
    json.dump(res, open(RES, "w"))
    if a.write:
        write_db(eng, res)


def write_db(eng, res):
    rows = [(eid, v.get("relative"), v.get("key"), v["basis"], json.dumps({"google_trend_relative": {
        "source": "pytrends", "anchor": G.ANCHOR_TOPIC, "anchor_label": G.ANCHOR_LABEL, "geo": G.GEO, "timeframe": G.TIMEFRAME,
        "recent_delta_pct": v.get("recent_delta_pct"), "entity_mean": v.get("entity_mean"), "anchor_mean": v.get("anchor_mean"),
        "basis": v["basis"]}})) for eid, v in res.items() if v.get("relative") is not None or v["basis"] == "none"]
    with eng.begin() as c:
        for i in range(0, len(rows), 500):
            ch = rows[i:i + 500]
            r = c.execute(text("""
                UPDATE entity_metrics m SET google_trend_relative = t.rel, google_trend_topic = t.topic, google_trend_basis = t.basis,
                       signal_provenance = COALESCE(m.signal_provenance, '{}'::jsonb) || CAST(t.prov AS jsonb)
                FROM unnest(CAST(:ids AS uuid[]), CAST(:rel AS float8[]), CAST(:topic AS text[]), CAST(:basis AS text[]), CAST(:prov AS text[]))
                     AS t(eid, rel, topic, basis, prov)
                WHERE m.entity_id = t.eid AND m.time = (SELECT max(time) FROM entity_metrics x WHERE x.entity_id = t.eid)"""),
                {"ids": [r_[0] for r_ in ch], "rel": [r_[1] for r_ in ch], "topic": [r_[2] for r_ in ch],
                 "basis": [r_[3] for r_ in ch], "prov": [r_[4] for r_ in ch]})
            print("written", r.rowcount)


if __name__ == "__main__":
    if "--write-only" in sys.argv:
        eng = create_engine(settings.POSTGRES_SYNC_URL)
        write_db(eng, load_res())
    else:
        main()

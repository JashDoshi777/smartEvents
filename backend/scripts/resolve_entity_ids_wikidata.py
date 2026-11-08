"""
Step 2 — exact external IDs from Wikidata (SPARQL, VALUES batches of 50 QIDs, <=1 req/s).

For every active entity with external_ids.wikidata_qid, fetch P2397 (YouTube channel), P434 (MusicBrainz),
P646 (Freebase/KG id -> Google Trends topic id), P1902 (Spotify), P2003 (Instagram), P2002 (Twitter),
P27 (citizenship), P495 (country of origin), P17 (country; fallback for teams/venues), P31, P106, label, aliases.

Stores everything in entities.external_ids['wikidata'] = {..., 'provenance': {source, qid, retrieved_at}}.
Existing top-level external_ids keys are never touched. Idempotent: re-running overwrites only the 'wikidata' blob.
Raw responses are cached in the scratchpad so the run is resumable.

Usage: python scripts/resolve_entity_ids_wikidata.py [--dry-run] [--refresh]
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text
from app.core.config import settings

PROPS = {"P2397": "youtube_channel_id", "P434": "musicbrainz_id", "P646": "freebase_id", "P1902": "spotify_id",
         "P2003": "instagram", "P2002": "twitter", "P27": "P27", "P495": "P495", "P17": "P17", "P31": "P31", "P106": "P106"}


def query(qids):
    vals = " ".join(f"wd:{q}" for q in qids)
    pp = " ".join(f"wdt:{p}" for p in PROPS)
    return f"""SELECT ?q ?pp ?v ?vLabel WHERE {{
  VALUES ?q {{ {vals} }}
  {{ VALUES ?pp {{ {pp} }} ?q ?pp ?v . }}
  UNION {{ ?q rdfs:label ?v . FILTER(lang(?v)="en") BIND("label" AS ?pp) }}
  UNION {{ ?q schema:description ?v . FILTER(lang(?v)="en") BIND("desc" AS ?pp) }}
  UNION {{ ?q skos:altLabel ?v . FILTER(lang(?v)="en") BIND("alias" AS ?pp) }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def fetch_batch(qids, refresh=False):
    import hashlib
    key = "wd_ids2_" + hashlib.md5(",".join(sorted(qids)).encode()).hexdigest()
    p = _wd._cache_path(key)
    if os.path.exists(p) and not refresh:
        return json.load(open(p))
    for attempt in range(4):
        r = _wd.get(_wd.WD_SPARQL, {"query": query(qids), "format": "json"}, min_gap=1.1, timeout=120)
        if r is not None:
            rows = r.json()["results"]["bindings"]
            json.dump(rows, open(p, "w"))
            return rows
        time.sleep(5)
    raise RuntimeError("SPARQL batch failed")


def parse(rows):
    out = {}
    for b in rows:
        q = b["q"]["value"].rsplit("/", 1)[-1]
        d = out.setdefault(q, {"label": None, "aliases": [], "P27": [], "P495": [], "P17": [], "P31": [], "P106": []})
        pp = b["pp"]["value"].rsplit("/", 1)[-1]
        v = b["v"]["value"]
        if pp == "label":
            d["label"] = v
        elif pp == "desc":
            d["description"] = v
        elif pp == "alias":
            d["aliases"].append(v)
        elif pp in ("P27", "P495", "P17", "P31", "P106"):
            d[pp].append({"qid": v.rsplit("/", 1)[-1], "label": b.get("vLabel", {}).get("value")})
        else:
            lst = d.setdefault(PROPS[pp], [])
            if v not in lst:
                lst.append(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        ents = c.execute(text("select id::text id, external_ids->>'wikidata_qid' q from entities where status='active' and external_ids->>'wikidata_qid' is not null")).mappings().all()
    qids = sorted({e["q"] for e in ents})
    print(len(ents), "entities,", len(qids), "distinct QIDs")
    data = {}
    for i in range(0, len(qids), 50):
        data.update(parse(fetch_batch(qids[i:i + 50], a.refresh)))
        print("batch", i // 50 + 1, "done", flush=True)
    now = datetime.now(timezone.utc).isoformat()
    upd = []
    for e in ents:
        d = data.get(e["q"])
        if d is None:
            continue
        blob = {k: v for k, v in d.items() if v not in (None, [], "")}
        blob["provenance"] = {"source": "wikidata-sparql", "qid": e["q"], "retrieved_at": now}
        upd.append({"id": e["id"], "b": json.dumps(blob)})
    print("resolved", len(upd), "of", len(ents), "; missing from Wikidata:", len(ents) - len(upd))
    if a.dry_run:
        return
    with eng.begin() as c:
        for i in range(0, len(upd), 100):
            c.execute(text("""update entities x set external_ids = coalesce(x.external_ids,'{}'::jsonb) || jsonb_build_object('wikidata', v.b::jsonb),
                              signal_ids_resolved_at = now()
                              from (select (e->>'id')::uuid id, e->>'b' b from jsonb_array_elements(cast(:j as jsonb)) e) v where x.id=v.id"""),
                      {"j": json.dumps(upd[i:i + 100])})
    print("written", len(upd))


if __name__ == "__main__":
    main()

"""
Conservative Wikidata QID discovery for entities that lack one (they cannot get exact IDs otherwise).

For each active entity without external_ids.wikidata_qid: wbsearchentities (<=1 req/s), then wbgetentities on the candidates.
A candidate is ACCEPTED only if (a) its en label or alias equals the entity name after normalisation, (b) its English description
matches the entity type (artist: singer/musician/rapper/DJ/band/...; comedian: comedian/stand-up; movie: film), and
(c) it is the ONLY candidate satisfying (a)+(b). Ambiguous or empty -> left unresolved. Nothing is guessed.
Accepted QIDs are written with data_provenance.qid_discovery = {method, retrieved_at, label, description}.

Usage: python scripts/discover_missing_qids.py [--dry-run] --csv PATH
"""
import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.services.entity_identity import norm_name

DESC = {
    "artist": re.compile(r"singer|musician|rapper|dj\b|disc jockey|band|composer|record producer|songwriter|group|duo|ensemble|producer|vocalist|instrumentalist|rock|electronic|indie", re.I),
    "comedian": re.compile(r"comedian|stand-up|comic", re.I),
    "movie": re.compile(r"\bfilm\b|movie", re.I),
}


def candidates(name):
    r = _wd.get(_wd.WD_API, dict(action="wbsearchentities", search=name, language="en", uselang="en", type="item", limit=50, format="json"), min_gap=1.05)
    return [x["id"] for x in (r.json().get("search", []) if r else [])]


def details(qids):
    r = _wd.get(_wd.WD_API, dict(action="wbgetentities", ids="|".join(qids), props="labels|aliases|descriptions", languages="en", format="json"), min_gap=1.05)
    return (r.json().get("entities", {}) if r else {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--csv", required=True)
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        rows = c.execute(text("select id::text id, name, name_aliases, entity_type from entities where status='active' and external_ids->>'wikidata_qid' is null and entity_type in ('artist','comedian','movie')")).mappings().all()
    now = datetime.now(timezone.utc).isoformat()
    out, acc = [], []
    for r in rows:
        targets = {norm_name(r["name"])} | {norm_name(x) for x in (r["name_aliases"] or [])}
        cands = candidates(r["name"])
        ent = details(cands) if cands else {}
        ok = []
        for q, e in ent.items():
            labels = [e.get("labels", {}).get("en", {}).get("value", "")] + [x["value"] for x in e.get("aliases", {}).get("en", [])]
            desc = e.get("descriptions", {}).get("en", {}).get("value", "")
            if any(norm_name(l) in targets for l in labels if l) and DESC[r["entity_type"]].search(desc):
                ok.append((q, labels[0], desc))
        status = "accepted" if len(ok) == 1 else ("ambiguous" if ok else "none")
        out.append({"name": r["name"], "type": r["entity_type"], "status": status, "candidates": json.dumps(ok)})
        if status == "accepted":
            acc.append({"id": r["id"], "q": ok[0][0], "label": ok[0][1], "desc": ok[0][2]})
        print(r["name"], "->", status, ok[0][0] if status == "accepted" else "", flush=True)
    with open(a.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "type", "status", "candidates"])
        w.writeheader()
        w.writerows(out)
    if a.dry_run:
        return
    with eng.begin() as c:
        for x in acc:
            c.execute(text("""update entities set external_ids = coalesce(external_ids,'{}'::jsonb) || jsonb_build_object('wikidata_qid', cast(:q as text)),
                    data_provenance = coalesce(data_provenance,'{}'::jsonb) || cast(:p as jsonb) where id=cast(:id as uuid) and external_ids->>'wikidata_qid' is null"""),
                      {"id": x["id"], "q": x["q"], "p": json.dumps({"qid_discovery": {"method": "wbsearchentities exact-label + type-description, unique candidate", "retrieved_at": now, "label": x["label"], "description": x["desc"]}})})
    print("accepted", len(acc), "of", len(rows))


if __name__ == "__main__":
    main()

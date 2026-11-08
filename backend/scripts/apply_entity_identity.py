"""
Steps 5+6 — nationality / market classification, dedupe, canonical names. Source of truth: external_ids.wikidata
(written by resolve_entity_ids_wikidata.py). Changes are made ONLY where Wikidata gives a citable value.

 * entities.nationality  <- P27 / P495 / P17 (first available), 'India' if India is among the values
 * is_international: nationality India -> False (+ primary_market 'India' if it was not); non-India -> True, primary_market
   left untouched and data_provenance.india_audience=true is recorded when primary_market == 'India'
 * duplicates (same wikidata_qid, or same normalised name + type): keep the row with most data active, others
   status='inactive', data_provenance.merged_into=<id> + merge_reason. Rows are never deleted.
 * name == Wikidata label up to case/diacritics/punctuation/spacing -> name := label, old name kept in name_aliases.
 * data_provenance.wikidata_identity = {label, aliases, qid, retrieved_at}

Writes a CSV of every changed row. Idempotent. Usage: python scripts/apply_entity_identity.py [--dry-run] --csv PATH
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, ".")
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.services.entity_identity import classify_nationality, norm_name, spelling_only_diff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--csv", required=True)
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        rows = c.execute(text("""select e.id::text id, e.name, e.name_aliases, e.entity_type, e.primary_market, e.is_international, e.nationality,
                 e.external_ids, e.data_provenance, e.status,
                 (select count(*) from entity_metrics m where m.entity_id=e.id) n_metrics,
                 (select count(*) from events v where v.entity_id=e.id) n_events
                 from entities e where e.status='active'""")).mappings().all()
    changes, updates = [], defaultdict(dict)   # updates[id] = {col: value}
    now = datetime.now(timezone.utc).isoformat()

    def log(r, field, old, new, reason):
        changes.append({"id": r["id"], "name": r["name"], "entity_type": r["entity_type"], "field": field, "old": old, "new": new, "reason": reason})

    # ---- dedupe
    groups = defaultdict(list)
    for r in rows:
        q = (r["external_ids"] or {}).get("wikidata_qid")
        if q:
            groups[("qid", q)].append(r)
        groups[("name", norm_name(r["name"]), r["entity_type"])].append(r)
    merged = set()
    for k, g in groups.items():
        g = [r for r in g if r["id"] not in merged]
        if len(g) < 2 or (k[0] == "name" and not k[1]):
            continue
        if k[0] == "name":
            qs = {(r["external_ids"] or {}).get("wikidata_qid") for r in g} - {None}
            if len(qs) > 1:
                continue  # different Wikidata entities that merely share a name: NOT duplicates
        keep = max(g, key=lambda r: (bool((r["external_ids"] or {}).get("wikidata_qid")), r["n_metrics"] + r["n_events"], len(r["external_ids"] or {})))
        for r in g:
            if r is keep:
                continue
            merged.add(r["id"])
            reason = f"duplicate of '{keep['name']}' ({'same wikidata_qid' if k[0]=='qid' else 'same normalised name+type'})"
            updates[r["id"]]["status"] = "inactive"
            updates[r["id"]]["prov"] = {"merged_into": keep["id"], "merge_reason": reason, "merged_at": now}
            log(r, "status", "active", "inactive", reason + f" -> merged_into={keep['id']}")

    # ---- nationality / market / names / identity blob
    for r in rows:
        if r["id"] in merged:
            continue
        wd = (r["external_ids"] or {}).get("wikidata")
        if not wd:
            continue
        u = updates[r["id"]]
        prov = u.setdefault("prov", {})
        prov["wikidata_identity"] = {"label": wd.get("label"), "aliases": wd.get("aliases", [])[:20], "qid": (r["external_ids"] or {}).get("wikidata_qid"),
                                     "retrieved_at": (wd.get("provenance") or {}).get("retrieved_at")}
        nat = classify_nationality(r["entity_type"], wd.get("P27", []), wd.get("P495", []), wd.get("P17", []), wd.get("description"))
        # A human correction (data_provenance.manual_override on nationality/is_international) always wins over Wikidata.
        _mo = (r["data_provenance"] or {}).get("manual_override") or {}
        if _mo.get("field") in ("is_international", "nationality"):
            nat = None
        if nat and nat["nationality"]:
            if r["nationality"] != nat["nationality"]:
                u["nationality"] = nat["nationality"]
                log(r, "nationality", r["nationality"], nat["nationality"], f"Wikidata {nat['via']}={nat['all']} {nat['note']}".strip())
            if nat["is_india"] and r["is_international"]:
                u["is_international"] = False
                log(r, "is_international", True, False, f"Wikidata {nat['via']} includes India (Q668)")
                if r["primary_market"] != "India":
                    u["primary_market"] = "India"
                    log(r, "primary_market", r["primary_market"], "India", "Indian nationality (domestic)")
            elif not nat["is_india"] and not r["is_international"]:
                u["is_international"] = True
                log(r, "is_international", False, True, f"Wikidata {nat['via']}={nat['all']} (not India) {nat['note']}".strip())
                if r["primary_market"] == "India":
                    prov["india_audience"] = True
                    prov["india_audience_note"] = "non-Indian nationality per Wikidata; kept primary_market=India (tours/charts in India)"
        label = wd.get("label")
        if label and spelling_only_diff(r["name"], label):
            u["name"] = label
            al = list(r["name_aliases"] or [])
            if r["name"] not in al:
                al.append(r["name"])
            u["name_aliases"] = al
            log(r, "name", r["name"], label, "differs from Wikidata label only by case/diacritics/spacing; old kept in name_aliases")

    with open(a.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "entity_type", "field", "old", "new", "reason"])
        w.writeheader()
        w.writerows(changes)
    by = defaultdict(int)
    for ch in changes:
        by[ch["field"]] += 1
    print("changes by field:", dict(by), "| merged:", len(merged))
    if a.dry_run:
        return
    with eng.begin() as c:
        for uid, u in updates.items():
            c.execute(text("""update entities set
                  status = coalesce(:status, status), nationality = coalesce(:nat, nationality),
                  is_international = coalesce(cast(:intl as boolean), is_international), primary_market = coalesce(:pm, primary_market),
                  name = coalesce(:name, name), name_aliases = coalesce(cast(:al as varchar[]), name_aliases),
                  data_provenance = coalesce(data_provenance,'{}'::jsonb) || cast(:prov as jsonb)
                  where id = cast(:id as uuid)"""),
                      {"id": uid, "status": u.get("status"), "nat": u.get("nationality"), "intl": u.get("is_international"), "pm": u.get("primary_market"),
                       "name": u.get("name"), "al": u.get("name_aliases"), "prov": json.dumps(u.get("prov", {}))})
    print("applied", len(updates))


if __name__ == "__main__":
    main()

"""Backfill entities.name_aliases from Wikidata (en + hi labels/aliases via wbgetentities, 50 ids per call) plus the
aliases already stored in external_ids.wikidata.aliases and the old spellings kept by apply_entity_identity.py.

Rules: de-duplicated (case/diacritic-insensitive), never equals the entity name, single-token aliases that are English
dictionary words / generic names are dropped, aliases claimed by >1 active entity are dropped (ambiguous), <= 60 chars.
Existing aliases are preserved (union). Provenance: data_provenance.alias_backfill {source, retrieved_at, added}.
Idempotent. DRY-RUN by default; pass --apply to write.   Usage: python scripts/backfill_aliases.py [--apply]"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.entity_identity import is_generic_name as dict_generic, norm_name
from app.services.news_filter import is_generic_name as news_generic


DESCRIPTORS = {"singer", "actor", "actress", "rapper", "comedian", "musician", "playback", "indian", "band", "film", "movie",
               "dj", "king", "queen", "composer", "singing", "producer", "director", "artist", "team", "club", "of", "the", "maestro", "short", "films", "star", "legend", "voice", "prince", "princess"}


def keep(alias: str, etype: str = "artist") -> bool:
    a = (alias or "").strip()
    if len(a) < 3 or len(a) > 60 or "(" in a:
        return False
    words = set(norm_words(a))
    if words & DESCRIPTORS:
        return False   # epithets/descriptions ("Indian singer", "King of Playback Singing"), not names
    if len(a.split()) == 1 and etype not in ("artist", "comedian"):
        return False      # one-word aliases of teams/films/places ('Kerala') are homonym-prone
    if len(a.split()) == 1 and (dict_generic(a) or news_generic(a) or len(norm_name(a)) < 4):
        return False
    return True


def norm_words(s):
    import re
    return re.findall(r"[a-z]+", norm_name_spaced(s))


def norm_name_spaced(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()


def fetch(qids):
    out = {}
    for i in range(0, len(qids), 50):
        chunk = qids[i:i + 50]
        r = _wd.get(_wd.WD_API, dict(action="wbgetentities", ids="|".join(chunk), props="aliases|labels",
                                     languages="en|hi", format="json"), min_gap=0.3)
        if not r:
            print("batch failed", i)
            continue
        for q, e in r.json().get("entities", {}).items():
            vals = [v["value"] for l in ("en", "hi") for v in e.get("aliases", {}).get(l, [])]
            vals += [e["labels"][l]["value"] for l in ("en", "hi") if l in e.get("labels", {})]
            out[q] = vals
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        rows = c.execute(text("""select id::text id, name, entity_type, coalesce(name_aliases,'{}') al, external_ids->>'wikidata_qid' qid,
                 external_ids->'wikidata'->'aliases' wal,
                 data_provenance->'alias_backfill'->'added' prev from entities where status='active'""")).mappings().all()
    qids = sorted({r["qid"] for r in rows if r["qid"]})
    wd = fetch(qids)
    cand, claim = {}, defaultdict(set)
    for r in rows:
        names = {norm_name(r["name"])}
        vals = list(r["al"]) + list(r["wal"] or []) + wd.get(r["qid"], [])
        out, seen = [], set(names)
        for v in vals:
            k = norm_name(v)
            if not k or k in seen or not keep(v, r["entity_type"]):
                continue
            seen.add(k)
            out.append(v.strip())
            claim[k].add(r["id"])
        cand[r["id"]] = out
    for r in rows:   # a name claimed as an alias by another entity, or equal to another entity's name, is ambiguous
        pass
    all_names = defaultdict(set)
    for r in rows:
        all_names[norm_name(r["name"])].add(r["id"])
    ups, added_total = [], 0
    for r in rows:
        final = [v for v in cand[r["id"]] if len(claim[norm_name(v)]) == 1
                 and not (all_names.get(norm_name(v), set()) - {r["id"]})]
        # always keep pre-existing aliases (they were curated by earlier steps)
        prev_bad = {v for v in (r["prev"] or []) if not keep(v, r["entity_type"])}     # prune earlier backfill output that fails today's rules
        old = [v for v in r["al"] if v not in prev_bad]
        final = list(dict.fromkeys([*old, *final]))
        new = [v for v in final if v not in r["al"]]
        if new or prev_bad:
            ups.append({"id": r["id"], "al": final, "added": [v for v in final if v in (set(new) | set(r["prev"] or []))]})
            added_total += len(new)
    print(f"{len(rows)} active entities, {len(qids)} QIDs; {len(ups)} entities gain aliases (+{added_total})")
    for u in ups[:12]:
        print("  ", u["id"][:8], u["added"][:6])
    if not a.apply:
        print("dry-run (use --apply)")
        return
    now = datetime.now(timezone.utc).isoformat()
    with eng.begin() as c:
        for i in range(0, len(ups), 100):
            c.execute(text("""update entities e set name_aliases = cast(x.al as varchar[]),
                    data_provenance = coalesce(e.data_provenance,'{}'::jsonb) || jsonb_build_object('alias_backfill',
                        jsonb_build_object('source','wikidata wbgetentities en|hi aliases+labels','retrieved_at', cast(:now as text), 'added', x.added))
                  from (select (j->>'id')::uuid id, (select array_agg(v) from jsonb_array_elements_text(j->'al') v) al, j->'added' added
                        from jsonb_array_elements(cast(:j as jsonb)) j) x where e.id = x.id"""),
                      {"j": json.dumps(ups[i:i + 100]), "now": now})
    print("applied", len(ups))


if __name__ == "__main__":
    main()

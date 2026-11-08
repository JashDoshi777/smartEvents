"""Fetch (and cache on disk) Wikidata facts for entities: sitelinks (en/hi), label, P646 (Google KG id), P31 classes.
Used by backfill_attention.py and collect_google_trends_relative.py. Never writes entities.external_ids.
Cache: $LIVEIQ_CACHE/wd_facts.json {qid: {...}} (resumable)."""
import json
import os
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd

CACHE = os.path.join(_wd.CACHE_DIR, "wd_facts.json")


def load():
    try:
        return json.load(open(CACHE))
    except Exception:  # noqa: BLE001
        return {}


def fetch_facts(qids, refresh=False):
    facts = load()
    todo = [q for q in dict.fromkeys(qids) if refresh or q not in facts]
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        r = _wd.get(_wd.WD_API, dict(action="wbgetentities", ids="|".join(chunk), props="sitelinks|claims|labels",
                                     languages="en", format="json"), min_gap=0.3)
        if not r:
            continue
        for q, e in r.json().get("entities", {}).items():
            if "missing" in e:
                facts[q] = {"missing": True}
                continue
            s, cl = e.get("sitelinks", {}), e.get("claims", {})
            p646 = [c["mainsnak"]["datavalue"]["value"] for c in cl.get("P646", []) if "datavalue" in c.get("mainsnak", {})]
            p31 = [c["mainsnak"]["datavalue"]["value"]["id"] for c in cl.get("P31", []) if "datavalue" in c.get("mainsnak", {})]
            facts[q] = {"en": (s.get("enwiki") or {}).get("title"), "hi": (s.get("hiwiki") or {}).get("title"),
                        "label": (e.get("labels", {}).get("en") or {}).get("value"), "p646": p646, "p31": p31,
                        "redirect_to": None}
        json.dump(facts, open(CACHE, "w"))
        print(f"wd facts {min(i + 50, len(todo))}/{len(todo)}", flush=True)
    return facts

"""
Fill lat/lng (and capacity when Wikidata has P1083 and ours is NULL) for the hand-seeded venues from Wikidata.
A match requires: normalised label/alias equals the venue name (or one contains the other, >= 8 chars),
the item has P625 coordinates, and lies within 30 km of the venue's city centre. Never overwrites existing values.
Usage: python scripts/enrich_seed_venue_coords.py [--dry-run]
"""
import json
import math
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text
from app.core.config import settings


def hav(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def main():
    dry = "--dry-run" in sys.argv
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        rows = c.execute(text("select v.id,v.name,v.city,v.total_capacity,ci.lat,ci.lng from venues v join cities ci on ci.name=v.city "
                              "where v.lat is null and v.data_provenance is null")).all()
    ups = []
    for id_, name, city, cap, clat, clng in rows:
        base = name.split(",")[0]
        qs = _wd.cached("search_venue_" + _wd.norm(base).replace(" ", "_")[:60], lambda b=base: _wd.search(b, limit=6))
        ents = _wd.get_entities(qs, need_v=2)
        nn = _wd.norm(base)
        best = None
        for q in qs:
            e = ents.get(q)
            if not e or not e["claims"].get("P625"):
                continue
            names = {_wd.norm(e["label"] or "")} | {_wd.norm(a) for a in e["aliases"]}
            if not (nn in names or any(len(n) >= 8 and (n in nn or nn in n) for n in names)):
                continue
            la, lo = e["claims"]["P625"][0]
            if hav(clat, clng, la, lo) > 30:
                continue
            best = (q, e, la, lo); break
        if best:
            q, e, la, lo = best
            wcap = next((int(v["amount"]) for v in e["claims"].get("P1083", []) if isinstance(v, dict)), None)
            ups.append((id_, name, q, la, lo, wcap if cap is None else None, wcap, cap))
            print("match", name, "->", q, e["label"], round(la, 4), round(lo, 4), "cap", wcap, "(ours", cap, ")")
        else:
            print("no match", name)
    print(f"matched {len(ups)}/{len(rows)}")
    if dry:
        return
    with eng.begin() as c:
        for id_, name, q, la, lo, wcap, wcap_all, ours in ups:
            prov = {"source": "wikidata", "source_id": q, "retrieved": _wd.TODAY, "fields": ["lat", "lng"] + (["total_capacity"] if wcap else []),
                    "note": "seeded row (scripts/seed_venues.py): other fields are editorial and unverified"}
            if wcap_all and ours and wcap_all != ours:
                prov["capacity_discrepancy"] = {"seeded": ours, "wikidata_p1083": wcap_all, "action": "kept seeded value; review"}
            c.execute(text("update venues set lat=:la, lng=:lo, total_capacity=coalesce(total_capacity,:cap), data_provenance=CAST(:p AS jsonb), updated_at=now() where id=:i"),
                      {"la": la, "lo": lo, "cap": wcap, "p": json.dumps(prov), "i": id_})
        # seeded rows without a match still get an explicit provenance note
        c.execute(text("""update venues set data_provenance=CAST(:p AS jsonb) where data_provenance is null"""),
                  {"p": json.dumps({"source": "seed", "retrieved": None, "note": "hand-seeded (scripts/seed_venues.py); no cited source; coordinates/capacity unverified"})})
    print("written")


if __name__ == "__main__":
    main()

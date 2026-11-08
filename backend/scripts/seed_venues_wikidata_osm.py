"""
Phase B2 — real venues for tracked Indian cities from Wikidata (+ OpenStreetMap Overpass).

* Wikidata: items located in India whose instance-of is (a subclass of) stadium, arena, concert hall,
  theatre building, convention centre, amphitheatre, auditorium, multi-purpose hall, performing arts
  centre, nightclub, event venue, exhibition park, cricket field, sports complex. Capacity = P1083
  (only if present), coordinates = P625.
* OSM Overpass (--osm): named nodes/ways tagged leisure=stadium, amenity=theatre|events_venue|
  conference_centre|nightclub|arts_centre within RADIUS_KM of each tracked city centre. Capacity only
  from a numeric `capacity` tag; address/pincode from addr:* tags when present.
* A venue is attached to the nearest tracked city within ASSIGN_KM (haversine on real coordinates);
  otherwise it is skipped (counted).
* Dedupe: vs existing venues (same city + normalised name, or <250 m apart) and across sources.
* Unknown attributes (indoor/parking/alcohol/fill rate/price/rating) stay NULL — never defaulted.
Provenance goes in venues.data_provenance: {source, source_id, retrieved, capacity_source, license}.

Usage: python scripts/seed_venues_wikidata_osm.py [--dry-run] [--osm] [--wikidata-only]
"""
import argparse
import json
import os
import math
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text
from app.core.config import settings

ASSIGN_KM = 30
RADIUS_KM = 12
INDIA_BBOX = (6.0, 68.0, 37.5, 97.5)  # S, W, N, E

WD_TYPES = {  # qid -> our venue_type
    "Q483110": "stadium", "Q682943": "stadium", "Q641226": "arena", "Q1060829": "theatre", "Q24354": "theatre",
    "Q1378975": "convention_centre", "Q54831": "amphitheatre", "Q230752": "theatre", "Q1763828": "arena",
    "Q3469910": "theatre", "Q622425": "club", "Q18674739": "other",
    "Q7579839": "sports_complex",
}
OSM_TYPES = [
    ('"leisure"="stadium"', "stadium", ["music", "sports"]),
    ('"amenity"="theatre"', "theatre", ["theatre", "comedy", "music"]),
    ('"amenity"="events_venue"', "other", []),
    ('"amenity"="conference_centre"', "convention_centre", []),
    ('"amenity"="arts_centre"', "theatre", []),
    ('"amenity"="nightclub"', "club", ["music"]),
]


def hav(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def in_india(lat, lng):
    return INDIA_BBOX[0] <= lat <= INDIA_BBOX[2] and INDIA_BBOX[1] <= lng <= INDIA_BBOX[3]


def wd_venues():
    out = {}
    for qt, vt in WD_TYPES.items():
        q = f"""SELECT ?v ?vLabel ?coord ?cap ?website WHERE {{
          ?v wdt:P31/wdt:P279* wd:{qt}; wdt:P17 wd:Q668; wdt:P625 ?coord.
          OPTIONAL {{?v wdt:P1083 ?cap}} OPTIONAL {{?v wdt:P856 ?website}}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}"""
        try:
            rows = _wd.sparql(q, "venues_" + qt)
        except Exception as e:  # noqa
            print("SPARQL failed for", qt, e); continue
        for r in rows:
            qid = r["v"]["value"].rsplit("/", 1)[1]
            name = r["vLabel"]["value"]
            if name == qid:
                continue  # unlabeled
            lng, lat = [float(x) for x in r["coord"]["value"][6:-1].split()]
            d = out.setdefault(qid, {"qid": qid, "name": name, "lat": lat, "lng": lng, "types": set(), "cap": None})
            d["types"].add(vt)
            if "cap" in r:
                try:
                    cap = int(float(r["cap"]["value"]))
                    d["cap"] = max(d["cap"] or 0, cap)
                except ValueError:
                    pass
        print(qt, vt, len(rows))
    return list(out.values())


OSM_GROUPS = [OSM_TYPES[0:2], OSM_TYPES[2:4], OSM_TYPES[4:6]]  # stadium+theatre ; events_venue+conference ; arts_centre+nightclub
OVERPASS_ENDPOINTS = ["https://overpass.kumi.systems/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
                      "https://overpass-api.de/api/interpreter"]


def overpass_query(q):
    """Try each public endpoint politely; never accept a timed-out/partial answer."""
    for ep in OVERPASS_ENDPOINTS:
        r = _wd.get(ep, {"data": q}, min_gap=1.5, timeout=100, tries=1)
        if r is None:
            continue
        try:
            j = r.json()
        except ValueError:
            continue
        rem = j.get("remark") or ""
        if "timed out" in rem or "error" in rem.lower():
            continue
        return j["elements"]
    raise RuntimeError("all overpass endpoints failed")


def osm_venues(cities, cached_only=False):
    out = []
    for cname, lat, lng in cities:
        for gi, grp in enumerate(OSM_GROUPS):
            parts = "".join(f'nwr[{sel}][name](around:{RADIUS_KM * 1000},{lat},{lng});' for sel, _, _ in grp)
            q = f"[out:json][timeout:60];({parts});out center tags 400;"

            def run(q=q):
                return overpass_query(q)
            key = "osm3_" + _wd.norm(cname).replace(" ", "_") + f"_{gi}"
            try:
                if cached_only and not os.path.exists(_wd._cache_path(key)):
                    continue
                els = _wd.cached(key, run)
            except Exception as e:  # noqa
                print("overpass failed", cname, gi, e, flush=True); continue
            for el in els:
                t = el.get("tags", {})
                la = el.get("lat") or (el.get("center") or {}).get("lat")
                lo = el.get("lon") or (el.get("center") or {}).get("lon")
                if la is None:
                    continue
                vt, cats = "other", []
                for sel, v, c in OSM_TYPES:
                    k, val = [x.strip('"') for x in sel.split("=")]
                    if t.get(k) == val:
                        vt, cats = v, c; break
                raw_cap = str(t.get("capacity", "")).replace(",", "").strip()
                cap = int(raw_cap) if raw_cap.isdigit() else None
                out.append({"osm": f"{el['type']}/{el['id']}", "name": t["name"], "lat": la, "lng": lo, "type": vt, "cats": cats,
                            "cap": cap, "addr": ", ".join(t[k] for k in ("addr:housenumber", "addr:street", "addr:suburb", "addr:city") if k in t) or None,
                            "pin": t.get("addr:postcode")})
            print("osm", cname, gi, len(els), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--osm", action="store_true")
    ap.add_argument("--osm-cached-only", action="store_true", help="use only OSM results already cached (no Overpass calls)")
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        cities = [(r[0], r[1], r[2], r[3]) for r in c.execute(text("select name,lat,lng,state from cities where lat is not null"))]
        pops = {r[0]: r[1] for r in c.execute(text("select name,population from cities"))}
        existing = [dict(r) for r in c.execute(text("select name,city,lat,lng,data_provenance from venues")).mappings()]
    cl = [(n, la, lo) for n, la, lo, _ in cities]
    state = {n: s for n, _, _, s in cities}

    def nearest(lat, lng):
        best = min(cl, key=lambda c: hav(lat, lng, c[1], c[2]))
        d = hav(lat, lng, best[1], best[2])
        return (best[0], d) if d <= ASSIGN_KM else (None, d)

    cands = []
    skipped = {"outside_cities": 0, "not_india": 0}
    for v in wd_venues():
        if not in_india(v["lat"], v["lng"]):
            skipped["not_india"] += 1; continue
        city, d = nearest(v["lat"], v["lng"])
        if not city:
            skipped["outside_cities"] += 1; continue
        vt = sorted(v["types"], key=["stadium", "arena", "amphitheatre", "theatre", "convention_centre", "club", "sports_complex", "other"].index)[0]
        cands.append({"name": v["name"], "type": vt, "city": city, "lat": v["lat"], "lng": v["lng"], "cap": v["cap"], "addr": None, "pin": None,
                      "cats": [], "prov": {"source": "wikidata", "source_id": v["qid"], "retrieved": _wd.TODAY,
                                           "capacity_source": "wikidata P1083" if v["cap"] else None, "license": "CC0"}})
    if a.osm or a.osm_cached_only:
        for v in osm_venues(sorted(cl, key=lambda c: -(pops.get(c[0]) or 0)), cached_only=a.osm_cached_only):
            if not in_india(v["lat"], v["lng"]):
                continue
            city, d = nearest(v["lat"], v["lng"])
            if not city:
                skipped["outside_cities"] += 1; continue
            cands.append({"name": v["name"], "type": v["type"], "city": city, "lat": v["lat"], "lng": v["lng"], "cap": v["cap"],
                          "addr": v["addr"], "pin": v["pin"], "cats": v["cats"],
                          "prov": {"source": "openstreetmap", "source_id": v["osm"], "retrieved": _wd.TODAY,
                                   "capacity_source": "osm capacity tag" if v["cap"] else None, "license": "ODbL"}})
    # dedupe
    keep, stats = [], {"dup_existing": 0, "dup_cross": 0}
    pool = [(norm_, e["city"], e["lat"], e["lng"]) for e in existing for norm_ in [_wd.norm(e["name"])]]
    # wikidata first (richer ids), then osm
    cands.sort(key=lambda x: 0 if x["prov"]["source"] == "wikidata" else 1)
    for v in cands:
        nn = _wd.norm(v["name"])
        dup = False
        for pn, pc, pla, plo in pool:
            if (pc == v["city"] and (pn == nn or (len(nn) > 6 and (nn in pn or pn in nn) and (pla is None or hav(v["lat"], v["lng"], pla, plo) < 2)))) \
                    or (pla is not None and hav(v["lat"], v["lng"], pla, plo) < 0.25):
                dup = True; break
        if dup:
            stats["dup_existing"] += 1; continue
        keep.append(v)
        pool.append((nn, v["city"], v["lat"], v["lng"]))
    # within-run duplicates counted via pool (cross-source) — approximate stat
    print("candidates", len(cands), "keep", len(keep), stats, skipped)
    from collections import Counter
    print(Counter(v["city"] for v in keep).most_common(60))
    print(Counter(v["type"] for v in keep))
    print("with capacity:", sum(1 for v in keep if v["cap"]))
    if a.dry_run:
        return
    with eng.begin() as c:
        for v in keep:
            c.execute(text("""insert into venues (id,name,venue_type,city,state,country,address,pincode,lat,lng,total_capacity,
                suitable_categories,is_indoor,has_parking,is_alcohol_permitted,total_events_hosted,amenities,is_active,
                data_provenance,created_at,updated_at)
                values (gen_random_uuid(),:name,:type,:city,:state,'India',:addr,:pin,:lat,:lng,:cap,:cats,NULL,NULL,NULL,0,'{}',true,
                CAST(:prov AS jsonb),now(),now())"""),
                      {**v, "state": state[v["city"]], "prov": json.dumps(v["prov"])})
        # keep cities.active_venues_count in step with reality
        c.execute(text("update cities c set active_venues_count=(select count(*) from venues v where v.city=c.name and v.is_active)"))
    print("written", len(keep))


if __name__ == "__main__":
    main()

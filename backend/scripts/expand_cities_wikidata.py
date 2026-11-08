"""
Phase B1 — expand `cities` to top Indian live-event markets using Wikidata (REAL data only).

Per city we write: state, lat/lng (P625), population (P1082; Census-2011 statement preferred,
else the latest dated statement, year recorded), google_trends_geo_code (state's ISO 3166-2, P300),
tier (documented rule below) and data_provenance. Everything else stays NULL:
  * metro_population / avg_monthly_income / youth_population_pct — no sourced figure available;
  * nightlife/sports/arts/comedy/music scores — the 12 seeded rows carry hand-assigned editorial
    scores (scripts/seed_cities.py); there is no data source to derive them, so new rows stay NULL
    and the API treats NULL scores as "not yet scored".
Tier rule for NEW cities (documented, applied only to new rows):
  population >= 2,000,000 -> 2 ; >= 500,000 -> 3 ; else 4.   (tier 1 stays the 4 seeded metros)

Also audits the 12 seeded cities against Wikidata (population/coordinates) and, with --fix-existing,
corrects population only where Wikidata carries a Census-2011 statement that differs
(old->new logged in the provenance and printed).

Usage: python scripts/expand_cities_wikidata.py [--dry-run] [--fix-existing]
"""
import argparse
import json
import math
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text
from app.core.config import settings
from enrich_entities_wikidata import INDIAN_STATES

# (our display name, wikidata search term)
NEW = [
    ("Lucknow", "Lucknow"), ("Surat", "Surat"), ("Nagpur", "Nagpur"), ("Bhubaneswar", "Bhubaneswar"),
    ("Coimbatore", "Coimbatore"), ("Visakhapatnam", "Visakhapatnam"), ("Guwahati", "Guwahati"),
    ("Thiruvananthapuram", "Thiruvananthapuram"), ("Bhopal", "Bhopal"), ("Patna", "Patna"),
    ("Dehradun", "Dehradun"), ("Shillong", "Shillong"), ("Mysuru", "Mysore"), ("Vadodara", "Vadodara"),
    ("Ludhiana", "Ludhiana"), ("Kanpur", "Kanpur"), ("Nashik", "Nashik"), ("Ranchi", "Ranchi"),
    ("Raipur", "Raipur"), ("Amritsar", "Amritsar"), ("Jodhpur", "Jodhpur"), ("Udaipur", "Udaipur"),
    ("Varanasi", "Varanasi"), ("Madurai", "Madurai"), ("Mangaluru", "Mangalore"), ("Srinagar", "Srinagar"),
    ("Kozhikode", "Kozhikode"), ("Agra", "Agra"),
    ("Vijayawada", "Vijayawada"), ("Rajkot", "Rajkot"), ("Jamshedpur", "Jamshedpur"),
    ("Prayagraj", "Prayagraj"), ("Puducherry", "Puducherry"), ("Gangtok", "Gangtok"), ("Imphal", "Imphal"),
    ("Goa", "Goa"), ("Thrissur", "Thrissur"), ("Kolhapur", "Kolhapur"), ("Jabalpur", "Jabalpur"),
    ("Meerut", "Meerut"), ("Tiruchirappalli", "Tiruchirappalli"),
]
FIX_OK = {"Kolkata"}
EXISTING = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Pune", "Chennai", "Kolkata", "Ahmedabad", "Jaipur",
            "Chandigarh", "Kochi", "Indore"]
DB_NAME = {"Delhi": "Delhi NCR"}
OK_P31 = ("city", "town", "municipal", "state", "urban", "metropolis", "capital", "union territory", "agglomeration")


def pop_of(e):
    vals = [v for v in e["claims"].get("P1082", []) if isinstance(v, dict)]
    if not vals:
        return None, None
    c11 = [v for v in vals if v["year"] == "2011"]
    if c11:
        return int(c11[0]["amount"]), 2011
    dated = sorted([v for v in vals if v["year"]], key=lambda v: v["year"])
    if dated:
        return int(dated[-1]["amount"]), int(dated[-1]["year"])
    # Undated statement: usable only below 3M (larger undated values are district/agglomeration-level, e.g. Prayagraj 5.95M)
    v = int(vals[0]["amount"])
    return (v, None) if v <= 3_000_000 else (None, None)


def resolve(term):
    qs = _wd.cached("search_city_" + _wd.norm(term).replace(" ", "_"), lambda: _wd.search(term, limit=6))
    ents = _wd.get_entities(qs, need_v=2)
    need = {x for e in ents.values() for x in e["claims"].get("P31", [])}
    lab = _wd.labels(sorted(need))
    for q in qs:
        e = ents.get(q)
        if not e or IN_ not in e["claims"].get("P17", []):
            continue
        p31 = " ".join((lab.get(x) or "").lower() for x in e["claims"].get("P31", []))
        if any(k in p31 for k in OK_P31):
            return q, e
    return None, None


IN_ = "Q668"


def state_of(e):
    # P131 first; P1376 ("capital of") only when the item has no P131 (e.g. Thiruvananthapuram)
    frontier = [x for x in (e["claims"].get("P131") or e["claims"].get("P1376") or []) if isinstance(x, str)]
    own = e["label"]
    if own in INDIAN_STATES:
        return own, e
    for _ in range(5):
        if not frontier:
            break
        ents = _wd.get_entities(frontier, need_v=2)
        nxt = []
        for q in frontier:
            x = ents.get(q)
            if not x:
                continue
            if x["label"] in INDIAN_STATES:
                return x["label"], x
            nxt += [y for y in (x["claims"].get("P131") or x["claims"].get("P1376") or []) if isinstance(y, str)]
        frontier = nxt
    # last resort: the Wikidata description itself names the state ("metropolis in Tamil Nadu, India")
    desc = e.get("desc") or ""
    hit = [st for st in INDIAN_STATES if st in desc]
    if len(hit) == 1:
        return hit[0], None
    return None, None


def hav(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fix-existing", action="store_true")
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        have = {r["name"]: dict(r) for r in c.execute(text("select * from cities")).mappings()}

    ins, upd, audit = [], [], []
    for disp, term in [(DB_NAME.get(n, n), n) for n in EXISTING] + NEW:
        is_existing = disp in have
        q, e = resolve(term)
        if not q:
            print("UNRESOLVED", disp); continue
        pop, yr = pop_of(e)
        st, st_e = state_of(e)
        coord = (e["claims"].get("P625") or [None])[0]
        geo = (st_e["claims"].get("P300") or [None])[0] if st_e else None
        prov = {"source": "wikidata", "wikidata_qid": q, "retrieved": _wd.TODAY, "population_year": yr,
                "population_basis": "Census of India via Wikidata P1082" if yr == 2011 else "Wikidata P1082 latest dated statement",
                "state_qid_source": "P131 chain", "notes": []}
        if disp == "Goa":
            prov["notes"].append("Goa is a state-level item; used as a market region (Panaji/Margao/Candolim belt).")
        if is_existing:
            row = have[disp]
            d = {"city": disp, "qid": q, "db_pop": row["population"], "wd_pop": pop, "wd_year": yr}
            if coord and row["lat"] is not None:
                d["coord_km"] = round(hav(row["lat"], row["lng"], coord[0], coord[1]), 1)
            audit.append(d)
            p = dict(row["data_provenance"] or {})
            p.update({"wikidata_qid": q, "audited": _wd.TODAY,
                      "curated_unverified_fields": ["metro_population", "avg_monthly_income", "youth_population_pct",
                                                    "nightlife_score", "sports_affinity_score", "arts_culture_score",
                                                    "comedy_market_size", "music_market_size", "festival_months",
                                                    "avg_temperature_jun_sep"],
                      "note": "seeded manually (scripts/seed_cities.py); no cited source for the listed fields"})
            sets = {"data_provenance": json.dumps(p)}
            # Wikidata carries 2011 *provisional* figures for some cities (Hyderabad, Pune) while our DB has the
            # final census count; and definitional differences for others (Delhi NCT vs MCD, Indore UA vs MC).
            # Only cases verified as provisional->final are corrected.
            if a.fix_existing and disp in FIX_OK and yr == 2011 and pop and row["population"] != pop:
                p["population_correction"] = {"old": row["population"], "new": pop, "source": "Census of India 2011 via Wikidata " + q,
                                              "date": _wd.TODAY}
                sets["data_provenance"] = json.dumps(p); sets["population"] = pop
            upd.append((disp, sets))
            continue
        tier = None if not pop else 2 if pop >= 2_000_000 else 3 if pop >= 500_000 else 4
        ins.append({"name": disp, "state": st, "tier": tier, "population": pop, "lat": coord[0] if coord else None,
                    "lng": coord[1] if coord else None, "geo": geo, "prov": json.dumps(prov)})
    print("\nAUDIT existing cities (db vs wikidata):")
    for d in audit:
        print(d)
    print(f"\nnew cities to insert: {len(ins)}")
    for r in ins:
        print(r["name"], r["state"], r["tier"], r["population"], r["lat"], r["lng"], r["geo"])
    if a.dry_run:
        return
    with eng.begin() as c:
        for disp, sets in upd:
            cols = ", ".join(f"{k}=CAST(:{k} AS jsonb)" if k == "data_provenance" else f"{k}=:{k}" for k in sets)
            c.execute(text(f"update cities set {cols}, updated_at=now() where name=:n"), {**sets, "n": disp})
        for r in ins:
            c.execute(text("""insert into cities (id,name,state,country,tier,population,lat,lng,google_trends_geo_code,
                    active_on_district,district_events_count,competitor_events_count,active_venues_count,
                    top_categories,monsoon_months,festival_months,data_provenance,created_at,updated_at)
                    values (gen_random_uuid(),:name,:state,'India',:tier,:population,:lat,:lng,:geo,false,0,0,0,
                    '{}','{}','{}',CAST(:prov AS jsonb),now(),now()) on conflict (name) do nothing"""), r)
    print("written")


if __name__ == "__main__":
    main()

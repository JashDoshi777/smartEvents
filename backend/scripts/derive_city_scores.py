"""
Derive city demographics + market scores from REAL sources for cities that have none (the 12 editorial cities are
NEVER overwritten; their derived values are stored only inside data_provenance for comparison).

youth_population_pct  Census of India 2011, table C-13 (single-year age returns, DISTRICT level, URBAN column,
                      censusindia.gov.in): sum(ages 18..35) / "All ages" for the district(s) containing the city.
                      provenance.youth: {source: 'census2011_c13_district_urban', districts: [...]}
avg_monthly_income    STATE-LEVEL PROXY: per-capita GSDP 2024-25 (Wikipedia "List of Indian states and UTs by GDP per
                      capita", which cites PRS India "Analysis of State Budgets"/MoSPI) / 12, INR per person per month.
                      NOT a city income and NOT comparable with the editorial household-income figures.
                      provenance.income: {source: 'state_proxy', basis: 'per_capita_gsdp_2024_25/12', state}
nightlife / music / comedy / sports / arts scores  (0-100)
  score_d = mean over components c of PR_c, PR_c = percentile rank of the city's count among ALL 53 cities,
            PR = (number of cities with a strictly smaller count) / (N-1) * 100   (ties share the lowest rank; 0 stays 0)
  components (counts):
    nightlife: OSM amenity in {bar,pub,nightclub} within a +-10 km bounding box around the city centre
    music    : OSM {amenity=nightclub|music_venue|concert_hall, live_music=yes} within the same box ; DB music events (city) ;
               DB artist entities with home_city = city
    comedy   : DB comedy events (city) ; DB comedian entities with home_city ; DB venues of type club/theatre... (venues
               with 'comedy' in suitable_categories)
    sports   : OSM leisure in {stadium, sports_hall} within the same box ; DB sports events (city) ; DB sports_team entities (home_city)
    arts     : OSM {amenity=theatre|arts_centre, tourism=gallery|museum} within the same box ; DB venues of type theatre/art_gallery
  Written: city.<score columns> only where currently NULL; data_provenance.scores_basis='derived' + scores_derived {..}.
Usage: python scripts/derive_city_scores.py [--apply] [--skip-osm]
"""
import argparse, io, json, math, os, re, sys, time
sys.path.insert(0, "."); sys.path.insert(0, "scripts")
import _wd, requests
from datetime import date
from sqlalchemy import create_engine, text
from app.core.config import settings

C13 = {  # state -> (catalog id, download id, file code) from https://censusindia.gov.in/nada/index.php/catalog/<id>
    "Andhra Pradesh": 1438, "Assam": 1440, "Bihar": 1441, "Chhattisgarh": 1443, "Goa": 1447, "Gujarat": 1448,
    "Jammu and Kashmir": 1451, "Jharkhand": 1452, "Karnataka": 1453, "Kerala": 1454, "Madhya Pradesh": 1456,
    "Maharashtra": 1457, "Manipur": 1458, "Meghalaya": 1459, "Odisha": 1462, "Puducherry": 1463, "Punjab": 1464,
    "Rajasthan": 1465, "Sikkim": 1466, "Tamil Nadu": 1467, "Uttar Pradesh": 1469, "Uttarakhand": 1470,
}
# city -> census 2011 district name(s) in its state file (the district containing the city)
DISTRICTS = {
    "Agra": ["Agra"], "Amritsar": ["Amritsar"], "Bhopal": ["Bhopal"], "Bhubaneswar": ["Khordha"], "Coimbatore": ["Coimbatore"],
    "Dehradun": ["Dehradun"], "Gangtok": ["East District"], "Goa": ["North Goa", "South Goa"], "Guwahati": ["Kamrup Metropolitan"],
    "Imphal": ["Imphal West", "Imphal East"], "Jabalpur": ["Jabalpur"], "Jamshedpur": ["Purbi Singhbhum"], "Jodhpur": ["Jodhpur"],
    "Kanpur": ["Kanpur Nagar"], "Kolhapur": ["Kolhapur"], "Kozhikode": ["Kozhikode"], "Lucknow": ["Lucknow"], "Ludhiana": ["Ludhiana"],
    "Madurai": ["Madurai"], "Mangaluru": ["Dakshina Kannada"], "Meerut": ["Meerut"], "Mysuru": ["Mysore"], "Nagpur": ["Nagpur"],
    "Nashik": ["Nashik"], "Patna": ["Patna"], "Prayagraj": ["Allahabad"], "Puducherry": ["Puducherry"], "Raipur": ["Raipur"],
    "Rajkot": ["Rajkot"], "Ranchi": ["Ranchi"], "Shillong": ["East Khasi Hills"], "Srinagar": ["Srinagar"], "Surat": ["Surat"],
    "Thiruvananthapuram": ["Thiruvananthapuram"], "Thrissur": ["Thrissur"], "Tiruchirappalli": ["Tiruchirappalli"],
    "Udaipur": ["Udaipur"], "Vadodara": ["Vadodara"], "Varanasi": ["Varanasi"], "Vijayawada": ["Krishna"],
    "Visakhapatnam": ["Visakhapatnam"],
}
OSM = {  # dimension -> overpass tag filters (one `out count` per filter group)
    "nightlife": ['[amenity~"^(bar|pub|nightclub)$"]'],
    "music": ['[amenity~"^(nightclub|music_venue|concert_hall)$"]', '[live_music=yes]'],
    "sports": ['[leisure~"^(stadium|sports_hall)$"]'],
    "arts": ['[amenity~"^(theatre|arts_centre)$"]', '[tourism~"^(gallery|museum)$"]'],
}
RADIUS = 10000
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter"]


def norm(s):
    return re.sub(r"[^a-z]+", "", (s or "").lower())


def census_state(state):
    """-> {district_norm: {'urban_all','urban_18_35','name'}} from the cached C-13 xls."""
    import xlrd
    cid = C13[state]
    path = os.path.join(_wd.CACHE_DIR, f"c13_{cid}.xls")
    if not os.path.exists(path):
        h = _wd.get(f"https://censusindia.gov.in/nada/index.php/catalog/{cid}", min_gap=1.0).text
        m = re.search(r'href="(https://censusindia.gov.in/nada/index.php/catalog/\d+/download/\d+/[^"]+)"', h)
        r = _wd.get(m.group(1), min_gap=1.0, timeout=120)
        open(path, "wb").write(r.content)
    sh = xlrd.open_workbook(path).sheet_by_index(0)
    out = {}
    for i in range(sh.nrows):
        row = sh.row_values(i)
        if len(row) < 12 or not str(row[3]).startswith("District"):
            continue
        name = re.sub(r"^District\s*-\s*|\s*\(\d+\)\s*$", "", str(row[3])).strip()
        d = out.setdefault(norm(name), {"name": name, "all": 0.0, "youth": 0.0})
        age = row[4]
        urban = row[11]
        if not isinstance(urban, float):
            continue
        if age == "All ages":
            d["all"] = urban
        elif isinstance(age, float) and 18 <= age <= 35:
            d["youth"] += urban
    return out


def youth_for(city, state, cache={}):
    if city not in DISTRICTS or state not in C13:
        return None
    if state not in cache:
        cache[state] = census_state(state)
    allp = yp = 0.0; names = []
    for dn in DISTRICTS[city]:
        d = cache[state].get(norm(dn))
        if not d or not d["all"]:
            return None
        allp += d["all"]; yp += d["youth"]; names.append(d["name"])
    return round(yp / allp * 100, 1), names


def nsdp():
    j = _wd.get("https://en.wikipedia.org/w/api.php", dict(action="parse", page="List_of_Indian_states_and_union_territories_by_GDP_per_capita",
                                                           prop="wikitext", format="json", formatversion=2), min_gap=1).json()
    t = j["parse"]["wikitext"]
    out = {}
    for blk in t.split("|-")[1:]:
        lines = [l.strip() for l in blk.strip().split("\n") if l.strip().startswith("|")]
        if len(lines) < 6:
            continue
        m = re.search(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", lines[1])
        v = re.sub(r"[^\d]", "", lines[4]) if lines[4].startswith("|₹") else ""
        if m and v:
            out[re.sub(r"\s*\(.*\)", "", m.group(1)).strip()] = int(v)
    return out


def overpass(q):
    for ep in ENDPOINTS:
        r = _wd.get(ep, {"data": q}, min_gap=3.0, tries=3, timeout=150)
        if r is not None:
            try:
                return r.json()
            except ValueError:
                continue
    raise RuntimeError("overpass failed")


def osm_counts(city, lat, lng):
    """One Overpass query per city: a +-RADIUS bounding box around the centre, one `out count` per tag group."""
    def run():
        d = RADIUS / 111000.0
        dl = d / math.cos(math.radians(lat))
        bb = f"({lat - d:.4f},{lng - dl:.4f},{lat + d:.4f},{lng + dl:.4f})"
        flat = [(dim, g) for dim, groups in OSM.items() for g in groups]
        q = "[out:json][timeout:120];" + "".join(f"nwr{g}{bb};out count;" for _, g in flat)
        els = overpass(q)["elements"]
        if len(els) != len(flat):
            raise RuntimeError("unexpected overpass result")
        res = {dim: [] for dim in OSM}
        for (dim, _), el in zip(flat, els):
            res[dim].append(int(el["tags"]["total"]))
        return res
    return _wd.cached("osmbbox_%d_%s" % (RADIUS, norm(city)), run)


def pr(values):
    n = len(values)
    return [sum(1 for w in values if w < v) / (n - 1) * 100 if n > 1 else 0.0 for v in values]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--skip-osm", action="store_true")
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL, pool_pre_ping=True)
    with eng.connect() as c:
        cities = [dict(r) for r in c.execute(text("select id,name,state,lat,lng,nightlife_score,youth_population_pct,avg_monthly_income,data_provenance from cities order by name")).mappings()]
        ev = {(r[0], r[1]): r[2] for r in c.execute(text("select city, category, count(*) from events where city is not null group by 1,2"))}
        en = {(r[0], r[1]): r[2] for r in c.execute(text("select home_city, entity_type, count(*) from entities where home_city is not null group by 1,2"))}
        vn = {(r[0], r[1]): r[2] for r in c.execute(text("select city, venue_type, count(*) from venues group by 1,2"))}
        vcomedy = {r[0]: r[1] for r in c.execute(text("select city, count(*) from venues where 'comedy' = any(suitable_categories) group by 1"))}
    names = [x["name"] for x in cities]
    osm = {}
    if not a.skip_osm:
        for x in cities:
            if x["lat"] is None:
                continue
            osm[x["name"]] = osm_counts(x["name"], x["lat"], x["lng"])
            print("osm", x["name"], osm[x["name"]], flush=True)
    comp = {d: {} for d in ("nightlife", "music", "comedy", "sports", "arts")}
    for n in names:
        o = osm.get(n)
        comp["comedy"][n] = [ev.get((n, "comedy"), 0), en.get((n, "comedian"), 0), vcomedy.get(n, 0)]
        if o is None:                      # no coordinates / OSM skipped -> OSM-based dimensions stay unscored
            for d in ("nightlife", "music", "sports", "arts"):
                comp[d][n] = None
            continue
        comp["nightlife"][n] = [o["nightlife"][0]]
        comp["music"][n] = [sum(o["music"]), ev.get((n, "music"), 0), en.get((n, "artist"), 0)]
        comp["sports"][n] = [o["sports"][0], ev.get((n, "sports"), 0), en.get((n, "sports_team"), 0)]
        comp["arts"][n] = [sum(o["arts"]), vn.get((n, "theatre"), 0) + vn.get((n, "art_gallery"), 0)]
    derived = {n: {} for n in names}
    for d, per in comp.items():
        ok = [n for n in names if per[n] is not None]
        k = len(next(iter(per[n] for n in ok))) if ok else 0
        ranks = [pr([per[n][i] for n in ok]) for i in range(k)]
        for j, n in enumerate(ok):
            derived[n][d] = {"score": round(sum(r[j] for r in ranks) / k, 1), "counts": per[n]}
    inc = nsdp()
    print("NSDP states parsed:", len(inc))
    today = _wd.TODAY
    updates = []
    for x in cities:
        n = x["name"]
        prov = dict(x["data_provenance"] or {})
        editorial = x["nightlife_score"] is not None
        sets, p = {}, {}
        if not editorial:
            for d, col in (("nightlife", "nightlife_score"), ("music", "music_market_size"), ("comedy", "comedy_market_size"),
                           ("sports", "sports_affinity_score"), ("arts", "arts_culture_score")):
                if d in derived[n]:
                    sets[col] = derived[n][d]["score"]
            if sets:
                p["scores_basis"] = "derived"
        else:
            p["scores_basis"] = "editorial"
            p["scores_derived_for_comparison"] = {d: v["score"] for d, v in derived[n].items()}
        if derived[n]:
            p["scores_derived"] = {"retrieved": today, "method": "percentile_rank_across_cities_v1", "radius_m": RADIUS,
                                   "osm": "overpass (ODbL)", "components": {d: v["counts"] for d, v in derived[n].items()}}
        if x["youth_population_pct"] is None:
            y = youth_for(n, x["state"])
            if y:
                sets["youth_population_pct"] = y[0]
                p["youth"] = {"source": "census2011_c13_district_urban", "districts": y[1], "ages": "18-35", "retrieved": today,
                              "note": "urban population of the district(s) containing the city"}
        if x["avg_monthly_income"] is None and x["state"] in inc:
            sets["avg_monthly_income"] = round(inc[x["state"]] / 12.0)
            p["income"] = {"source": "state_proxy", "basis": "per_capita_gsdp_2024_25/12", "state": x["state"], "state_per_capita_inr": inc[x["state"]],
                           "retrieved": today, "origin": "en.wikipedia List_of_Indian_states_and_union_territories_by_GDP_per_capita (cites PRS India)"}
        if p:
            prov.update(p)
            updates.append((x["id"], n, sets, prov))
    print("cities to update:", len(updates))
    for _, n, s, p in updates[:60]:
        print(f"  {n:20s}", {k: v for k, v in s.items()}, p.get("scores_basis"))
    if not a.apply:
        print("dry-run (use --apply)"); return
    with eng.begin() as c:
        for cid, n, s, p in updates:
            cols = "".join(f", {k} = :{k}" for k in s)
            c.execute(text(f"update cities set data_provenance = cast(:p as jsonb){cols}, updated_at = now() where id = :id"),
                      {"p": json.dumps(p), "id": cid, **s})
    print("applied", len(updates))


if __name__ == "__main__":
    main()

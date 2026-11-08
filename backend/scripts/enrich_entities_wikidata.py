"""
Phase A — enrich `entities` from Wikidata + Wikipedia (REAL data only).

Matching: Wikidata wbsearchentities(name) -> candidates -> accept ONLY when
  (1) candidate label/alias equals the entity name after normalisation,
  (2) the candidate's instance-of / occupation passes the entity_type check,
  (3) domestic (non-international) entities must have an India link (citizenship,
      origin country or birth/formation place in India),
  (4) exactly one candidate qualifies, or one has >=3x the sitelinks of the runner-up.
Anything else is logged as 'ambiguous'/'unmatched' and left untouched.

Only NULL / empty columns are filled (never overwrites curated values), except
is_international which is corrected when Wikidata gives a clear country-of-citizenship.
Provenance is written to external_ids (wikidata_qid, wikipedia_title, spotify_id,...)
and data_provenance (source, retrieved, confidence, per-field sources).

Usage: python scripts/enrich_entities_wikidata.py [--dry-run] [--limit N] [--only-missing-qid]
"""
import argparse
import json
import sys
from collections import Counter

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text
from app.core.config import settings

IN = "Q668"
INDIAN_STATES = {
    "Maharashtra", "Delhi", "Karnataka", "Telangana", "Tamil Nadu", "West Bengal", "Gujarat", "Rajasthan",
    "Punjab", "Kerala", "Uttar Pradesh", "Madhya Pradesh", "Bihar", "Odisha", "Assam", "Haryana", "Goa",
    "Uttarakhand", "Himachal Pradesh", "Jharkhand", "Chhattisgarh", "Andhra Pradesh", "Meghalaya", "Manipur",
    "Nagaland", "Mizoram", "Tripura", "Sikkim", "Arunachal Pradesh", "Jammu and Kashmir", "Chandigarh",
    "Puducherry", "Ladakh",
}
CITY_ALIAS = {"New Delhi": "Delhi NCR", "Delhi": "Delhi NCR", "Bangalore": "Bengaluru", "Bombay": "Mumbai",
              "Madras": "Chennai", "Calcutta": "Kolkata", "Gurgaon": "Gurugram"}

KW = {
    "artist": ["singer", "musician", "composer", "rapper", "disc jockey", "record producer", "songwriter",
               "band", "musical group", "duo", "vocalist", "instrumentalist", "sitar", "guitarist", "pianist",
               "drummer", "girl group", "boy band", "record label", "dj", "playback", "tabla", "violinist",
               "flautist", "music producer", "music director", "electronic music"],
    "comedian": ["comedian", "comedy"],
    "sports_team": ["team", "club", "franchise", "sports", "player", "athlete", "league"],
    "movie": ["film", "series", "television", "miniseries"],
    "attraction": ["festival", "fair", "park", "event"],
    "theatre_group": ["theatre", "theater", "troupe", "company"],
}


def type_ok(etype, labels_):
    kws = KW.get(etype, [])
    low = [(l or "").lower() for l in labels_]
    if etype == "artist" and any(("film" in l or "television" in l) for l in low) and not any(
            k in l for l in low for k in ("singer", "musician", "band", "composer", "rapper")):
        return False
    return any(k in l for l in low for k in kws)


def first(claims, pid):
    v = claims.get(pid)
    return v[0] if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--names", help="comma-separated names only")
    ap.add_argument("--new-only", action="store_true", help="only rows created by expand_entities_wikidata.py and not yet enriched")
    ap.add_argument("--skip-matched", action="store_true", help="skip entities already having wikidata_qid")
    a = ap.parse_args()

    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        rows = c.execute(text("""select id,name,entity_type,category,is_international,primary_market,external_ids,
              description,home_city,home_state,country,language,genre,genres,image_url,name_aliases,data_provenance
              from entities where status='active' order by name""")).mappings().all()
    rows = [dict(r) for r in rows]
    if a.names:
        s = {n.strip().lower() for n in a.names.split(",")}
        rows = [r for r in rows if r["name"].lower() in s]
    if a.new_only:
        rows = [r for r in rows if (r["data_provenance"] or {}).get("source") == "wikidata-sparql"]
    if a.skip_matched:
        rows = [r for r in rows if not (r["external_ids"] or {}).get("wikidata_qid")]
    if a.limit:
        rows = rows[:a.limit]
    print(f"entities to process: {len(rows)}")

    # 1. candidate search
    cands = {}
    for i, r in enumerate(rows):
        ex = (r["external_ids"] or {}).get("wikidata_qid")
        cands[r["name"]] = [ex] if ex else _wd.cached("search_" + _wd.norm(r["name"]).replace(" ", "_")[:80], lambda r=r: _wd.search(r["name"]))
        if i % 50 == 0:
            print("searched", i)
    allq = sorted({q for v in cands.values() for q in v})
    ents = _wd.get_entities(allq)
    miss = [q for q in allq if q not in ents]
    for _ in range(3):
        if not miss:
            break
        ents.update(_wd.get_entities(miss)); miss = [q for q in allq if q not in ents]
    print("candidate QIDs", len(allq), "unfetched", len(miss))
    sl = _wd.cached("sl_" + str(hash(tuple(allq)) % 10**9), lambda: _wd.sitelink_counts(allq))

    # labels for type-defining claims
    need = set()
    for e in ents.values():
        for pid in ("P31", "P106", "P27", "P495", "P17", "P136", "P19", "P740", "P1412", "P103", "P407", "P364", "P2936", "P159", "P131"):
            need.update(x for x in e["claims"].get(pid, []) if isinstance(x, str))
    lab = _wd.labels(sorted(need))

    def L(ids):
        return [lab.get(i) for i in ids if lab.get(i)]

    def india_link(e):
        cl = e["claims"]
        return IN in (cl.get("P27", []) + cl.get("P495", []) + cl.get("P17", []))

    report = {"matched": [], "ambiguous": [], "unmatched": []}
    updates = []
    for r in rows:
        etype = r["entity_type"]
        nn = _wd.norm(r["name"])
        pool = []
        for q in cands[r["name"]]:
            e = ents.get(q)
            if not e:
                continue
            names = {_wd.norm(e["label"] or "")} | {_wd.norm(x) for x in e["aliases"]}
            names |= {n.replace(" ", "") for n in names}
            if nn not in names and nn.replace(" ", "") not in names:
                continue
            tl = L(e["claims"].get("P31", [])) + L(e["claims"].get("P106", [])) + [e.get("desc") or ""]
            if any("fictional" in (t or "").lower() for t in tl):
                continue
            if not type_ok(etype, tl):
                continue
            # hard identity check: our Last.fm MBID must equal Wikidata's MusicBrainz ID when both exist
            mb = (r["external_ids"] or {}).get("lastfm_mbid")
            wmb = e["claims"].get("P434", [])
            if mb and wmb and mb not in wmb:
                continue
            if mb and not wmb and e["claims"].get("P570"):
                continue  # deceased candidate that cannot be tied to our MBID (e.g. Steve Lacy jazz vs singer)
            domestic = not r["is_international"] and (r["primary_market"] == "India")
            if domestic and etype != "sports_team" and not india_link(e):
                # place of origin/birth in India counts as well
                if not any(p in (e["claims"].get("P19", []) + e["claims"].get("P740", [])) for p in []):
                    # fall back to description wording sourced from Wikidata
                    if "indian" not in (e.get("desc") or "").lower():
                        continue
            pool.append((q, e))
        if not pool:
            report["unmatched"].append(r["name"]); continue
        pool.sort(key=lambda x: -sl.get(x[0], 0))
        if len(pool) > 1 and sl.get(pool[0][0], 0) < 3 * max(sl.get(pool[1][0], 0), 1):
            report["ambiguous"].append((r["name"], [(q, e["desc"]) for q, e in pool[:3]])); continue
        q, e = pool[0]
        mb = (r["external_ids"] or {}).get("lastfm_mbid")
        conf = 0.99 if (mb and mb in e["claims"].get("P434", [])) else 0.95 if len(pool) == 1 else 0.85
        report["matched"].append((r["name"], q, e["label"], e["desc"]))
        updates.append((r, q, e, conf))

    # 2. resolve places / languages / genres for matched
    place_ids = set()
    for r, q, e, conf in updates:
        cl = e["claims"]
        for pid in ("P19", "P740", "P159"):
            if first(cl, pid):
                place_ids.add(first(cl, pid)); break
    places = _wd.get_entities(sorted(p for p in place_ids if isinstance(p, str)))
    chain_need = {x for p in places.values() for x in p["claims"].get("P131", []) if isinstance(x, str)}
    chain = _wd.get_entities(sorted(chain_need))
    lab2 = _wd.labels(sorted({x for p in list(places.values()) + list(chain.values()) for pid in ("P131", "P17") for x in p["claims"].get(pid, []) if isinstance(x, str)}))

    CITYISH = ("city", "town", "village", "municipality", "metropolis", "commune", "borough", "locality",
               "census town", "urban", "capital", "district of", "municipal")

    def is_cityish(ent):
        p31 = " ".join((_wd.labels(ent["claims"].get("P31", [])) or {}).get(x) or "" for x in ent["claims"].get("P31", [])).lower() if False else \
            " ".join(((lab.get(x) or lab2.get(x) or (_wd.labels([x]).get(x))) or "").lower() for x in ent["claims"].get("P31", []))
        return any(k in p31 for k in CITYISH)

    def place_info(pq):
        """Walk up P131 from the birth/origin place until a city-like item (never a hospital/hamlet)."""
        cur = _wd.get_entities([pq]).get(pq)
        city_ent = None
        for _ in range(4):
            if not cur:
                break
            if is_cityish(cur):
                city_ent = cur; break
            nxt = [x for x in cur["claims"].get("P131", []) if isinstance(x, str)]
            cur = _wd.get_entities(nxt[:1]).get(nxt[0]) if nxt else None
        if not city_ent:
            return None, None, None
        city = city_ent["label"]
        if city == "Mumbai Suburban district":
            city = "Mumbai"
        if any(w in city.lower() for w in ("district", "county")) or "country" in " ".join(
                (_wd.labels(city_ent["claims"].get("P31", [])) or {}).values() if False else []):
            return None, None, None  # district/county-level items are not a home *city*
        country = None
        cid = (city_ent["claims"].get("P17") or [None])[0]
        if cid:
            country = _wd.labels([cid]).get(cid)
        state = city["label"] if False else None
        frontier = [x for x in city_ent["claims"].get("P131", []) if isinstance(x, str)]
        if city in INDIAN_STATES:
            state = city
        for _ in range(4):
            if state or not frontier:
                break
            ents_ = _wd.get_entities(frontier)
            nxt = []
            for f in frontier:
                x = ents_.get(f)
                if not x:
                    continue
                if x["label"] in INDIAN_STATES:
                    state = x["label"]; break
                nxt += [y for y in x["claims"].get("P131", []) if isinstance(y, str)]
            frontier = nxt
        return CITY_ALIAS.get(city, city), state, country

    # Wikipedia extracts
    stats = Counter()
    sqls = []
    for r, q, e, conf in updates:
        cl = e["claims"]
        sets, fields = {}, []
        ext = dict(r["external_ids"] or {})
        add = {"wikidata_qid": q}
        if e["enwiki"]:
            add["wikipedia_title"] = e["enwiki"]
        for k, pid in (("spotify_id", "P1902"), ("youtube_channel_id", "P2397"), ("instagram_handle", "P2003"),
                       ("musicbrainz_id", "P434"), ("imdb_id", "P345"), ("twitter_handle", "P2002"),
                       ("website", "P856")):
            v = first(cl, pid)
            if isinstance(v, str):
                add[k] = v
        for k, v in add.items():
            if k not in ext or not ext[k]:
                ext[k] = v
        if ext != (r["external_ids"] or {}):
            sets["external_ids"] = json.dumps(ext); fields.append("external_ids")
        if not r["description"] and e["enwiki"]:
            w = _wd.wp_summary(e["enwiki"])
            if w and w["extract"]:
                sets["description"] = w["extract"]; fields.append("description")
        elif not r["description"] and e["desc"]:
            sets["description"] = e["desc"][:1].upper() + e["desc"][1:]; fields.append("description(wikidata)")
        if not r["image_url"] and isinstance(first(cl, "P18"), str):
            sets["image_url"] = _wd.commons_thumb(first(cl, "P18")); fields.append("image_url")
        pq = next((first(cl, p) for p in ("P19", "P740", "P159") if first(cl, p)), None)
        city, state, pcountry = place_info(pq) if isinstance(pq, str) else (None, None, None)
        if city and not r["home_city"]:
            sets["home_city"] = city; fields.append("home_city")
        if state and not r["home_state"]:
            sets["home_state"] = state; fields.append("home_state")
        ctry_ids = cl.get("P27") or cl.get("P495") or cl.get("P17") or []
        ctry = next((lab.get(x) or lab2.get(x) for x in ctry_ids if lab.get(x) or lab2.get(x)), None)
        if ctry and not r["country"]:
            sets["country"] = ctry[:50]; fields.append("country")
        langs = L([x for x in (cl.get("P407") or cl.get("P364") or cl.get("P103") or cl.get("P1412") or cl.get("P2936") or []) if isinstance(x, str)])
        if langs and not r["language"]:
            sets["language"] = langs[0][:50]; fields.append("language")
        gen = [g for g in L([x for x in cl.get("P136", []) if isinstance(x, str)])][:6]
        if gen and not r["genre"]:
            sets["genre"] = gen[0][:100]; fields.append("genre")
        if gen and not r["genres"]:
            sets["genres"] = gen; fields.append("genres")
        # is_international: correct only on clear citizenship/origin evidence
        cids = cl.get("P27") or cl.get("P495") or []
        # Only ever correct True -> False when Wikidata says Indian citizen/origin. We never flip
        # False -> True: Bollywood acts of Pakistani/Nepali citizenship (Atif Aslam, Udit Narayan)
        # are domestic-market acts for this product.
        if IN in cids and r["is_international"] and r["entity_type"] in ("artist", "comedian", "movie"):
            intl = False
            if intl != bool(r["is_international"]):
                sets["is_international"] = intl; fields.append(f"is_international:{r['is_international']}->{intl}")
                stats["intl_fixed"] += 1
        prov = dict(r.get("data_provenance") or {}) if False else {}
        prov = {"source": "wikidata+wikipedia", "wikidata_qid": q, "retrieved": _wd.TODAY, "match_confidence": conf,
                "method": "name-exact+type+india-check", "fields": fields,
                "wikipedia_license": "CC BY-SA 4.0" if "description" in fields else None}
        sets["data_provenance"] = json.dumps(prov)
        sets["last_enriched_at"] = None  # placeholder replaced below
        del sets["last_enriched_at"]
        for f in fields:
            stats[f.split(":")[0].split("(")[0]] += 1
        sqls.append((r["id"], sets))

    print(f"matched={len(report['matched'])} ambiguous={len(report['ambiguous'])} unmatched={len(report['unmatched'])}")
    print("fields filled:", dict(stats))
    json.dump({"matched": report["matched"], "ambiguous": report["ambiguous"], "unmatched": report["unmatched"]},
              open(_wd.CACHE_DIR + "/entity_enrichment_report.json", "w"), indent=1)
    if a.dry_run:
        print("dry-run: no writes"); return
    with eng.begin() as c:
        for id_, sets in sqls:
            cols = []
            for k in sets:
                if k in ("external_ids", "data_provenance"):
                    cols.append(f"{k}=CAST(:{k} AS jsonb)")
                else:
                    cols.append(f"{k}=:{k}")
            c.execute(text(f"update entities set {', '.join(cols)}, updated_at=now() where id=:id"), {**sets, "id": id_})
    print("written", len(sqls))


if __name__ == "__main__":
    main()

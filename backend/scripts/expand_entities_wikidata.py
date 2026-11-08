"""
Phase C — expand `entities` with well-known, ACTIVE Indian performers / teams / festivals from Wikidata.

Selection (all via Wikidata SPARQL, nothing hand-typed):
  * musicians : alive, citizen of India, has a Spotify artist ID (P1902), NOT also an actor (film stars with soundtrack credits are excluded), occupation singer / musician / rapper / DJ / composer /
                songwriter / playback singer / record producer, with >= MIN_SL Wikipedia-language sitelinks
  * groups    : instance of musical group (or subclass), country of origin India, not dissolved, >= MIN_SL_GROUP sitelinks
  * comedians : alive, citizen of India, occupation (stand-up) comedian, >= MIN_SL_COMEDY sitelinks
  * teams     : member of league IPL / WPL / ISL / PKL / Hockey India League / Premier Badminton League /
                Pro Volleyball League / Ultimate Table Tennis, not dissolved
  * festivals : instance of music festival / film festival (religious festivals such as Diwali are excluded), country India, not dissolved, >= MIN_SL_FEST sitelinks
Deceased and dissolved items are skipped. Rows whose QID or normalised name already exists are skipped.
Inserted rows carry only identity facts (name/type/category/QID); `enrich_entities_wikidata.py --new-only`
then fills description/image/home city/etc from the QID, and the metrics collector fills real metrics.

Usage: python scripts/expand_entities_wikidata.py [--dry-run] [--min-sl 12]
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

OCC = {"Q177220": "singer", "Q639669": "musician", "Q2252262": "rapper", "Q130857": "DJ", "Q36834": "composer",
       "Q753110": "songwriter", "Q1755412": "playback singer", "Q183945": "record producer"}
LEAGUES = {  # league qid -> (genre label, sport category)
    "Q396412": ("IPL", "Cricket"), "Q115877036": ("WPL", "Cricket"), "Q16056350": ("ISL", "Football"),
    "Q17069491": ("PKL", "Kabaddi"), "Q4380931": ("Hockey India League", "Hockey"),
    "Q14191429": ("Premier Badminton League", "Badminton"), "Q60787154": ("Pro Volleyball League", "Volleyball"),
    "Q74112227": ("Ultimate Table Tennis", "Table Tennis"),
}


def vals(qs):
    return " ".join("wd:" + q for q in qs)


def run(name, q):
    return _wd.sparql(q, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-sl", type=int, default=12)
    ap.add_argument("--min-sl-group", type=int, default=6)
    ap.add_argument("--min-sl-comedy", type=int, default=4)
    ap.add_argument("--min-sl-fest", type=int, default=3)
    a = ap.parse_args()

    cand = {}  # qid -> dict

    def add(qid, name, etype, cat, genre, sl, kind):
        if name.startswith("Q") and name[1:].isdigit():
            return
        d = cand.setdefault(qid, {"qid": qid, "name": name, "type": etype, "cat": cat, "genre": genre, "sl": int(sl), "kind": kind})
        d["sl"] = max(d["sl"], int(sl))

    rows = run(f"musicians4_{a.min_sl}", f"""SELECT ?p ?pLabel (MAX(?sl) AS ?sitelinks) (GROUP_CONCAT(DISTINCT ?occ;separator="|") AS ?occs) WHERE {{
      VALUES ?occ {{ {vals(OCC)} }} ?p wdt:P106 ?occ; wdt:P27 wd:Q668; wdt:P1902 ?spotify; wikibase:sitelinks ?sl.
      FILTER NOT EXISTS {{ ?p wdt:P570 ?d }} FILTER NOT EXISTS {{ VALUES ?act {{ wd:Q33999 wd:Q10800557 wd:Q2405480 }} ?p wdt:P106 ?act }}
      FILTER(?sl >= {a.min_sl})
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }} }} GROUP BY ?p ?pLabel""")
    for r in rows:
        occs = [o.rsplit("/", 1)[1] for o in r["occs"]["value"].split("|")]
        cat = "Indian Hip-Hop" if "Q2252262" in occs else "Indian EDM" if "Q130857" in occs else "Music"
        add(r["p"]["value"].rsplit("/", 1)[1], r["pLabel"]["value"], "artist", cat, None, r["sitelinks"]["value"], "musician")
    rows = run(f"groups2_{a.min_sl_group}", f"""SELECT ?g ?gLabel (MAX(?sl) AS ?sitelinks) WHERE {{
      ?g wdt:P31/wdt:P279* wd:Q215380; wdt:P495 wd:Q668; wdt:P1902 ?spotify; wikibase:sitelinks ?sl.
      FILTER NOT EXISTS {{ ?g wdt:P576 ?d }} FILTER(?sl >= {a.min_sl_group})
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }} }} GROUP BY ?g ?gLabel""")
    for r in rows:
        add(r["g"]["value"].rsplit("/", 1)[1], r["gLabel"]["value"], "artist", "Music", None, r["sitelinks"]["value"], "group")
    rows = run(f"comedians2_{a.min_sl_comedy}", f"""SELECT ?p ?pLabel (MAX(?sl) AS ?sitelinks) WHERE {{
      ?p wdt:P106 wd:Q18545066; wdt:P27 wd:Q668; wikibase:sitelinks ?sl.
      FILTER NOT EXISTS {{ ?p wdt:P570 ?d }} FILTER(?sl >= {a.min_sl_comedy})
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }} }} GROUP BY ?p ?pLabel""")
    for r in rows:
        add(r["p"]["value"].rsplit("/", 1)[1], r["pLabel"]["value"], "comedian", "Stand-Up Comedy", "Stand-Up", r["sitelinks"]["value"], "comedian")
    rows = run("teams", f"""SELECT ?t ?tLabel ?league WHERE {{
      VALUES ?league {{ {vals(LEAGUES)} }} ?t wdt:P118 ?league.
      FILTER NOT EXISTS {{ ?t wdt:P576 ?d }} FILTER NOT EXISTS {{ ?t wdt:P31 wd:Q15275719 }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }} }}""")
    for r in rows:
        lq = r["league"]["value"].rsplit("/", 1)[1]
        g, cat = LEAGUES[lq]
        add(r["t"]["value"].rsplit("/", 1)[1], r["tLabel"]["value"], "sports_team", cat, g, 0, "team")
    rows = run(f"festivals2_{a.min_sl_fest}", f"""SELECT ?f ?fLabel (MAX(?sl) AS ?sitelinks) WHERE {{
      VALUES ?ft {{ wd:Q868557 wd:Q220505 }} ?f wdt:P31 ?ft; wdt:P17 wd:Q668; wikibase:sitelinks ?sl.
      FILTER NOT EXISTS {{ ?f wdt:P576 ?d }} FILTER(?sl >= {a.min_sl_fest})
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }} }} GROUP BY ?f ?fLabel""")
    for r in rows:
        add(r["f"]["value"].rsplit("/", 1)[1], r["fLabel"]["value"], "attraction", "Festival", "Festival", r["sitelinks"]["value"], "festival")

    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        ex = c.execute(text("select name, external_ids->>'wikidata_qid' from entities")).all()
    have_names = {_wd.norm(n) for n, _ in ex}
    have_q = {q for _, q in ex if q}
    new = []
    for d in sorted(cand.values(), key=lambda x: -x["sl"]):
        if d["qid"] in have_q or _wd.norm(d["name"]) in have_names:
            continue
        have_names.add(_wd.norm(d["name"]))
        new.append(d)
    print("candidates", len(cand), "new", len(new), dict(Counter(d["kind"] for d in new)))
    for d in new:
        print(" ", d["name"], d["kind"], d["sl"])
    if a.dry_run:
        return
    with eng.begin() as c:
        for d in new:
            prov = {"source": "wikidata-sparql", "wikidata_qid": d["qid"], "retrieved": _wd.TODAY, "selection": d["kind"],
                    "sitelinks": d["sl"], "method": "SPARQL: India-linked, alive/active, sitelink threshold"}
            c.execute(text("""insert into entities (id,name,name_aliases,entity_type,category,sub_categories,status,external_ids,
                country,genre,genres,primary_market,is_verified,is_international,is_active_on_district,is_featured,
                data_sources,data_provenance,created_at,updated_at)
                values (gen_random_uuid(),:name,'{}',:type,:cat,'{}','active',CAST(:ext AS jsonb),'India',:genre,:genres,'India',false,false,false,false,
                :ds,CAST(:prov AS jsonb),now(),now())"""),
                      {"name": d["name"][:255], "type": d["type"], "cat": d["cat"], "genre": d["genre"], "genres": [d["genre"]] if d["genre"] else [],
                       "ext": json.dumps({"wikidata_qid": d["qid"]}), "prov": json.dumps(prov),
                       "ds": ["youtube", "google_trends", "news"] + (["lastfm"] if d["type"] == "artist" else [])})
    print("inserted", len(new))


if __name__ == "__main__":
    main()

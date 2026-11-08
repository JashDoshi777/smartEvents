"""
Data-trust audit (read-only). Reports where entity identity / signals are suspect.

Usage: python scripts/data_trust_audit.py [--out path.json]
Prints a summary and writes full JSON (default: stdout summary only unless --out).
"""
import argparse
import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.services.entity_identity import NON_MUSIC_TYPES, is_generic_name, norm_name, title_similarity

LATEST = """
select distinct on (m.entity_id) m.entity_id, m.lastfm_listeners, m.lastfm_weekly_plays, m.youtube_subscribers,
       m.google_trend_score, m.spotify_followers, m.spotify_monthly_listeners
from entity_metrics m order by m.entity_id, m.time desc
"""


def run(c):
    rows = c.execute(text(f"""
      select e.id::text id, e.name, e.name_aliases, e.entity_type, e.country, e.primary_market, e.is_international,
             e.external_ids, e.data_provenance, e.nationality, m.*
      from entities e left join ({LATEST}) m on m.entity_id=e.id
      where e.status='active'""")).mappings().all()
    ind = [r for r in rows if not r["is_international"]]
    per_type = defaultdict(Counter)
    for r in ind:
        t = per_type[r["entity_type"]]
        t["entities"] += 1
        for k in ("lastfm_listeners", "youtube_subscribers", "google_trend_score", "spotify_followers"):
            if r[k] is not None:
                t[k] += 1
    out = {"active_total": len(rows), "active_indian_total": len(ind), "per_type_signal_counts": {k: dict(v) for k, v in per_type.items()}}
    out["contradictions"] = {
        "lastfm_lt_1000_and_youtube_gt_100k": [
            {"name": r["name"], "type": r["entity_type"], "lastfm": r["lastfm_listeners"], "yt": r["youtube_subscribers"]}
            for r in rows if r["lastfm_listeners"] is not None and r["lastfm_listeners"] < 1000 and (r["youtube_subscribers"] or 0) > 100_000],
        "non_music_with_lastfm": [
            {"name": r["name"], "type": r["entity_type"], "lastfm": r["lastfm_listeners"]}
            for r in rows if r["entity_type"] in NON_MUSIC_TYPES and r["lastfm_listeners"] is not None],
    }
    out["generic_name_risk"] = [{"name": r["name"], "type": r["entity_type"]} for r in rows if is_generic_name(r["name"])]
    by_q, by_n = defaultdict(list), defaultdict(list)
    for r in rows:
        q = (r["external_ids"] or {}).get("wikidata_qid")
        if q:
            by_q[q].append(r["name"])
        by_n[(norm_name(r["name"]), r["entity_type"])].append(r["name"])
    out["duplicate_candidates"] = {
        "same_qid": {q: v for q, v in by_q.items() if len(v) > 1},
        "same_normalised_name": {"|".join(map(str, k)): v for k, v in by_n.items() if len(v) > 1 and k[0]},
    }
    # YouTube channel title vs entity name (needs signal_validity from verify_entity_signals.py; absent => skipped)
    yt = c.execute(text(f"""select e.name, e.entity_type, m.signal_validity->>'youtube' v, m.signal_validity->'youtube_detail'->>'title' t,
         (m.signal_validity->'youtube_detail'->>'similarity')::float s from entities e join ({LATEST}) l on l.entity_id=e.id
         join entity_metrics m on m.entity_id=l.entity_id and m.time=(select max(time) from entity_metrics x where x.entity_id=e.id)
         where e.status='active' and m.signal_validity is not null""")).mappings().all()
    out["contradictions"]["youtube_title_not_similar"] = [dict(x) for x in yt if x["s"] is not None and x["s"] < 85]
    out["signal_validity_counts"] = {"youtube": dict(Counter(x["v"] for x in yt))}
    wd = [r for r in rows if r["nationality"]]
    conf = []
    for r in rows:
        nat = r["nationality"]
        if nat and not r["is_international"] and nat != "India":
            conf.append({"name": r["name"], "nationality": nat})
        elif nat == "India" and r["is_international"]:
            conf.append({"name": r["name"], "nationality": nat, "flag": "is_international but Indian"})
    out["nationality_conflicts"] = conf
    out["nationality_resolved"] = len(wd)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        res = run(c)
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1, default=str)
    s = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in res.items()}
    print(json.dumps(s, indent=1))
    for k, v in res["contradictions"].items():
        print(k, len(v))
    print("same_qid", len(res["duplicate_candidates"]["same_qid"]), "same_name", len(res["duplicate_candidates"]["same_normalised_name"]))
    print(json.dumps(res["per_type_signal_counts"], indent=0))

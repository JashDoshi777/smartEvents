"""
Steps 3+4 — verify YouTube / Last.fm identity BEFORE trusting a signal, and record verdicts in
entity_metrics.signal_validity (latest row per active entity). Existing metric values are never changed.

YouTube: channel id from Wikidata P2397 (external_ids.wikidata.youtube_channel_id); channels.list in batches of 50.
         A legacy name-searched id (external_ids.youtube_channel_id) is only *checked* (verdict name_match_unverified /
         title_mismatch), never promoted. No name search is ever performed.
Last.fm: artist.getInfo by MusicBrainz id (Wikidata P434 / legacy mbid). Without an MBID a name match is accepted only if
         the name is not generic AND top tags overlap expected genre/country. Non-artist types -> 'wrong_type' (no call).
trends/news/wiki -> 'pending' (owned by the methodology agent).

Usage: python scripts/verify_entity_signals.py [--dry-run] [--skip-lastfm] [--skip-youtube]
Resumable: API responses cached in the scratchpad cache dir.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import requests
import _wd
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.services.entity_identity import (MUSIC_TYPES, is_generic_name, lastfm_tag_overlap, lastfm_verdict,
                                          norm_name, youtube_verdict)

PENDING = {"trends": "pending", "news": "pending", "wiki": "pending"}


def cache_get(name):
    p = _wd._cache_path(name)
    return json.load(open(p)) if os.path.exists(p) else None


def cache_put(name, v):
    json.dump(v, open(_wd._cache_path(name), "w"))


def yt_channels(ids):
    out = {}
    todo = []
    for i in ids:
        v = cache_get("yt_" + i)
        if v is not None:
            out[i] = v or None
        else:
            todo.append(i)
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        r = requests.get("https://www.googleapis.com/youtube/v3/channels",
                         params={"part": "snippet,statistics", "id": ",".join(chunk), "maxResults": 50, "key": settings.YOUTUBE_API_KEY}, timeout=30)
        if r.status_code != 200:
            print("YouTube channels.list failed: HTTP", r.status_code)
            continue
        found = {}
        for it in r.json().get("items", []):
            st = it.get("statistics", {})
            found[it["id"]] = {"title": it["snippet"]["title"],
                               "subscribers": None if st.get("hiddenSubscriberCount") else int(st["subscriberCount"]) if "subscriberCount" in st else None}
        for cid in chunk:
            cache_put("yt_" + cid, found.get(cid, {}))
            out[cid] = found.get(cid)
    return out


def lastfm_call(params):
    key = "lfm_" + "_".join(f"{k}-{v}" for k, v in sorted(params.items())).replace("/", "_")[:180]
    v = cache_get(key)
    if v is not None:
        return v
    time.sleep(0.34)
    try:
        r = requests.get("https://ws.audioscrobbler.com/2.0/", params={**params, "method": "artist.getInfo", "api_key": settings.LASTFM_API_KEY, "format": "json"}, timeout=30)
        j = r.json() if r.status_code == 200 or r.headers.get("content-type", "").startswith("application/json") else {"error": r.status_code}
    except Exception as exc:  # noqa: BLE001
        print("lastfm error", type(exc).__name__)
        return {"error": "network"}
    if j.get("error") == 29:  # rate limit
        time.sleep(5)
        return {"error": 29}
    cache_put(key, j)
    return j


def slim_lfm(j):
    a = j.get("artist") if isinstance(j, dict) else None
    if not a:
        return None
    return {"name": a.get("name"), "mbid": a.get("mbid"), "listeners": int(a.get("stats", {}).get("listeners", 0) or 0),
            "tags": [t["name"] for t in a.get("tags", {}).get("tag", [])]}


def ratio_ok(a, b, k=3.0):
    if not a or not b:
        return None
    return (1 / k) <= (a / b) <= k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-lastfm", action="store_true")
    ap.add_argument("--skip-youtube", action="store_true")
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        rows = c.execute(text("""
          select e.id::text id, e.name, e.name_aliases, e.entity_type, e.genre, e.genres, e.category, e.primary_market, e.is_international,
                 e.external_ids, m.time, m.lastfm_listeners, m.youtube_subscribers
          from entities e left join lateral (select * from entity_metrics m where m.entity_id=e.id order by time desc limit 1) m on true
          where e.status='active' and m.time is not null""")).mappings().all()
    print(len(rows), "active entities with a latest metric row")
    now = datetime.now(timezone.utc).isoformat()

    # ---- YouTube
    ytmap = {}
    if not a.skip_youtube:
        ids = set()
        for r in rows:
            x = r["external_ids"] or {}
            ids.update(i for i in [(x.get("wikidata") or {}).get("youtube_channel_id", [None])[0], x.get("youtube_channel_id")] if i)
        print("YouTube channels to check:", len(ids))
        ytmap = yt_channels(sorted(ids))

    res = []
    cnt = {"yt": {}, "lfm": {}}
    for r in rows:
        x = r["external_ids"] or {}
        wd = x.get("wikidata") or {}
        names = [r["name"], *(r["name_aliases"] or []), *(wd.get("aliases") or [])]
        if wd.get("label"):
            names.append(wd["label"])
        v = {**PENDING}
        # YouTube
        wd_id = (wd.get("youtube_channel_id") or [None])[0]
        legacy = x.get("youtube_channel_id")
        if a.skip_youtube:
            yv = {"verdict": "skipped"}
        elif wd_id and ytmap.get(wd_id):
            yv = youtube_verdict(r["name"], names, ytmap[wd_id], "wikidata")
            yv["channel_id"] = wd_id
            yv["id_source"] = "wikidata:P2397"
            m = ratio_ok(r["youtube_subscribers"], ytmap[wd_id]["subscribers"])
            yv["metric_matches_channel"] = m
            if yv["verdict"] == "verified_wikidata" and m is False:
                yv["verdict"] = "metric_from_other_channel"  # id is exact, but the stored number came from a different channel
        elif legacy and ytmap.get(legacy) and not is_generic_name(r["name"]):
            yv = youtube_verdict(r["name"], names, ytmap[legacy], "legacy")
            if yv["verdict"] == "name_match_unverified" and ratio_ok(r["youtube_subscribers"], ytmap[legacy]["subscribers"]) is False:
                yv["verdict"] = "title_mismatch"
            yv["channel_id"] = legacy
            yv["id_source"] = "legacy_name_search"
        else:
            yv = {"verdict": "unresolved", "similarity": None}
            if legacy and ytmap.get(legacy):
                yv.update(legacy_channel_title=ytmap[legacy]["title"], note="generic name; legacy id not trusted")
        v["youtube"] = yv["verdict"]
        v["youtube_detail"] = yv
        cnt["yt"][yv["verdict"]] = cnt["yt"].get(yv["verdict"], 0) + 1
        # Last.fm
        lv = {"verdict": "wrong_type"}
        if r["entity_type"] in MUSIC_TYPES and not a.skip_lastfm:
            mbid = (wd.get("musicbrainz_id") or [None])[0] or x.get("lastfm_mbid") or x.get("musicbrainz_id")
            if mbid:
                info = slim_lfm(lastfm_call({"mbid": mbid}))
                if info:
                    lv = {"verdict": lastfm_verdict("artist", mbid_verified=True, name_match=True, generic=False, tags_ok=True, resolved=True),
                          "mbid": mbid, "lastfm_name": info["name"], "listeners": info["listeners"],
                          "metric_matches": ratio_ok(r["lastfm_listeners"], info["listeners"]), "id_source": "wikidata:P434" if wd.get("musicbrainz_id") else "legacy_mbid"}
                else:
                    mbid = None
            if not mbid or lv["verdict"] == "wrong_type":
                info = slim_lfm(lastfm_call({"artist": r["name"], "autocorrect": 0}))
                if not info:
                    lv = {"verdict": "unresolved"}
                else:
                    nm = norm_name(info["name"]) in {norm_name(n) for n in names}
                    india = (not r["is_international"]) and r["primary_market"] == "India"
                    tags_ok = lastfm_tag_overlap(info["tags"], [r["genre"], r["category"], *(r["genres"] or [])], india)
                    lv = {"verdict": lastfm_verdict("artist", mbid_verified=False, name_match=nm, generic=is_generic_name(r["name"]), tags_ok=tags_ok, resolved=True),
                          "lastfm_name": info["name"], "listeners": info["listeners"], "tags": info["tags"][:5], "generic": is_generic_name(r["name"]),
                          "id_source": "name_search"}
        elif r["entity_type"] in MUSIC_TYPES:
            lv = {"verdict": "skipped"}
        if lv.get("verdict") in ("verified_mbid", "name_verified_tags") and (lv.get("listeners") or 0) < 1000 \
                and yv.get("verdict") == "verified_wikidata" and (yv.get("subscribers") or 0) > 100_000:
            lv["suspect_split_entry"] = True  # exact id, but Last.fm page is tiny vs a huge verified YouTube channel: treat as weak
        v["lastfm"] = lv["verdict"]
        v["lastfm_detail"] = lv
        v["checked_at"] = now
        cnt["lfm"][lv["verdict"]] = cnt["lfm"].get(lv["verdict"], 0) + 1
        res.append({"id": r["id"], "time": r["time"].isoformat(), "v": v})
    print(json.dumps(cnt, indent=1))
    json.dump(res, open(_wd._cache_path("signal_validity_result"), "w"), default=str)
    if a.dry_run:
        return
    with eng.begin() as c:
        for i in range(0, len(res), 100):
            c.execute(text("""update entity_metrics m set signal_validity = x.v
                              from (select (e->>'id')::uuid id, (e->>'time')::timestamptz t, e->'v' v from jsonb_array_elements(cast(:j as jsonb)) e) x
                              where m.entity_id=x.id and m.time=x.t"""), {"j": json.dumps(res[i:i + 100])})
    print("written", len(res))


if __name__ == "__main__":
    main()

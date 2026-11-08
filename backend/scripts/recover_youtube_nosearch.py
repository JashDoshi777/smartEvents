"""YouTube channel recovery WITHOUT search.list (100 units): for entities whose signal_validity.youtube is 'unresolved'.
 (a) MusicBrainz artist url-relations (type 'youtube') for entities with a MusicBrainz id (1 req/s, descriptive UA);
 (b) Wikidata P11245 (YouTube handle) / P2397 for the rest;
 (c) resolve ids / handles with channels.list (id: batches of 50 = 1 unit/call; forHandle / forUsername: 1 unit/call);
 (d) VERIFY with the same helper as verify_entity_signals.py (title similarity >= 85 or full-name containment) plus a
     plausibility check (subscribers not hidden, >= 500); highest-subscriber verified channel wins.
Stores external_ids.youtube_channel_id (+ external_ids.youtube_recovery provenance), signal_validity.youtube =
'verified_musicbrainz' | 'verified_wikidata_handle' (+ youtube_detail) and youtube_subscribers on the entity's latest
metric row (updated in place). Never name-searches. Idempotent (only touches entities still 'unresolved').
DRY-RUN by default; --apply writes.   Usage: python scripts/recover_youtube_nosearch.py [--apply]"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
import requests
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.entity_identity import youtube_verdict

MB_UA = "LiveIQ-DataBot/1.0 (internal Zomato District analytics; jash.doshi@zomato.com)"
CH_RE = re.compile(r"youtube\.com/channel/(UC[0-9A-Za-z_-]{22})")
HANDLE_RE = re.compile(r"youtube\.com/(@[^/?#]+)")
USER_RE = re.compile(r"youtube\.com/user/([^/?#]+)")
C_RE = re.compile(r"youtube\.com/c/([^/?#]+)")
MIN_SUBS = 500


def cget(name):
    p = _wd._cache_path(name)
    return json.load(open(p)) if os.path.exists(p) else None


def cput(name, v):
    json.dump(v, open(_wd._cache_path(name), "w"))


def parse_yt_url(u):
    """-> ('id'|'handle'|'user', value) or None."""
    for rx, kind in ((CH_RE, "id"), (HANDLE_RE, "handle"), (USER_RE, "user"), (C_RE, "handle_c")):
        m = rx.search(u or "")
        if m:
            v = m.group(1)
            return (kind, v if kind != "handle_c" else "@" + v)
    return None


def mb_urls(mbid):
    k = "mbrel_" + mbid
    v = cget(k)
    if v is not None:
        return v
    time.sleep(1.1)
    try:
        r = requests.get(f"https://musicbrainz.org/ws/2/artist/{mbid}", params={"inc": "url-rels", "fmt": "json"},
                         headers={"User-Agent": MB_UA}, timeout=30)
    except requests.RequestException:
        return []
    if r.status_code == 503:
        time.sleep(5)
        return []
    if r.status_code != 200:
        cput(k, [])
        return []
    urls = [x["url"]["resource"] for x in r.json().get("relations", []) if x.get("type") == "youtube" and x.get("url")]
    cput(k, urls)
    return urls


def wd_claims(qids):
    out = {}
    for i in range(0, len(qids), 50):
        r = _wd.get(_wd.WD_API, dict(action="wbgetentities", ids="|".join(qids[i:i + 50]), props="claims", format="json"), min_gap=0.3)
        if not r:
            continue
        for q, e in r.json().get("entities", {}).items():
            cl = e.get("claims", {})
            vals = lambda p: [c["mainsnak"]["datavalue"]["value"] for c in cl.get(p, []) if "datavalue" in c.get("mainsnak", {})]
            out[q] = {"handles": ["@" + h.lstrip("@") for h in vals("P11245")], "ids": vals("P2397")}
    return out


def yt_call(params):
    k = "ytc_" + "_".join(f"{a}-{b}" for a, b in sorted(params.items())).replace("/", "_")[:180]
    v = cget(k)
    if v is not None:
        return v
    r = requests.get("https://www.googleapis.com/youtube/v3/channels", params={**params, "part": "snippet,statistics", "key": settings.YOUTUBE_API_KEY}, timeout=30)
    if r.status_code != 200:
        print("YouTube channels.list HTTP", r.status_code)
        return None
    items = []
    for it in r.json().get("items", []):
        st = it.get("statistics", {})
        items.append({"id": it["id"], "title": it["snippet"]["title"],
                      "subscribers": None if st.get("hiddenSubscriberCount") or "subscriberCount" not in st else int(st["subscriberCount"]),
                      "views": int(st["viewCount"]) if "viewCount" in st else None})
    cput(k, items)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        rows = c.execute(text("""select e.id::text id, e.name, e.name_aliases, e.external_ids, m.time
          from entities e join lateral (select time, signal_validity from entity_metrics where entity_id=e.id order by time desc limit 1) m on true
          where e.status='active' and m.signal_validity->>'youtube'='unresolved'""")).mappings().all()
    print(len(rows), "unresolved YouTube entities")
    qids = sorted({(r["external_ids"] or {}).get("wikidata_qid") for r in rows if (r["external_ids"] or {}).get("wikidata_qid")})
    cl = wd_claims(qids)
    cands = {}   # id -> list of (kind, value, source, url)
    n_mb = 0
    for r in rows:
        x = r["external_ids"] or {}
        wd = x.get("wikidata") or {}
        mbid = (wd.get("musicbrainz_id") or [None])[0] or x.get("musicbrainz_id")
        lst = []
        if mbid:
            urls = mb_urls(mbid)
            n_mb += 1
            for u in urls:
                p = parse_yt_url(u)
                if p:
                    lst.append((*p, "musicbrainz", u))
        q = x.get("wikidata_qid")
        for h in (cl.get(q) or {}).get("handles", []):
            lst.append(("handle", h, "wikidata_handle", f"wikidata:{q}:P11245"))
        for i in (cl.get(q) or {}).get("ids", []):
            lst.append(("id", i, "wikidata_handle", f"wikidata:{q}:P2397"))
        cands[r["id"]] = lst
    print("MusicBrainz lookups:", n_mb, "; entities with >=1 candidate:", sum(1 for v in cands.values() if v))
    # resolve
    ids = sorted({v for l in cands.values() for k, v, *_ in l if k == "id"})
    chan = {}
    for i in range(0, len(ids), 50):
        for it in yt_call({"id": ",".join(ids[i:i + 50]), "maxResults": 50}) or []:
            chan[it["id"]] = it
    byhandle = {}
    for l in cands.values():
        for k, v, *_ in l:
            if k in ("handle", "handle_c") and ("h", v) not in byhandle:
                items = yt_call({"forHandle": v})
                byhandle[("h", v)] = (items or [None])[0]
            elif k == "user" and ("u", v) not in byhandle:
                items = yt_call({"forUsername": v})
                byhandle[("u", v)] = (items or [None])[0]
    res, stats = [], {"verified_musicbrainz": 0, "verified_wikidata_handle": 0}
    for r in rows:
        names = [r["name"], *(r["name_aliases"] or []), *(((r["external_ids"] or {}).get("wikidata") or {}).get("aliases") or [])]
        best = None
        for k, v, src, url in cands[r["id"]]:
            ch = chan.get(v) if k == "id" else byhandle.get(("u" if k == "user" else "h", v))
            if not ch:
                continue
            vd = youtube_verdict(r["name"], names, ch, "wikidata")
            if vd["verdict"] != "verified_wikidata" or (ch["subscribers"] or 0) < MIN_SUBS:
                continue
            if (ch["title"] or "").strip().lower().endswith("- topic"):
                continue                     # auto-generated "Artist - Topic" channel: not the artist's own channel
            if best is None or (ch["subscribers"] or 0) > (best["ch"]["subscribers"] or 0):
                best = {"ch": ch, "src": src, "url": url, "sim": vd["similarity"]}
        if best:
            verdict = "verified_musicbrainz" if best["src"] == "musicbrainz" else "verified_wikidata_handle"
            stats[verdict] += 1
            res.append({"id": r["id"], "t": r["time"].isoformat(), "name": r["name"], "channel_id": best["ch"]["id"], "title": best["ch"]["title"],
                        "subs": best["ch"]["subscribers"], "views": best["ch"]["views"], "verdict": verdict, "url": best["url"], "sim": best["sim"]})
    print(stats, "of", len(rows))
    for x in res[:15]:
        print("  ", x["name"], "->", x["title"], x["subs"], x["verdict"])
    cput("youtube_recovery_result", res)
    if not a.apply:
        print("dry-run (use --apply)")
        return
    now = datetime.now(timezone.utc).date().isoformat()
    with eng.begin() as c:
        for i in range(0, len(res), 100):
            ch = res[i:i + 100]
            c.execute(text("""
              update entities e set external_ids = coalesce(e.external_ids,'{}'::jsonb) || jsonb_build_object(
                    'youtube_channel_id', x.cid, 'youtube_recovery', jsonb_build_object('source', x.verdict, 'url', x.url,
                    'channel_title', x.title, 'similarity', x.sim, 'retrieved', cast(:now as text), 'note', 'no search.list used'))
              from (select (j->>'id')::uuid id, j->>'channel_id' cid, j->>'verdict' verdict, j->>'url' url, j->>'title' title, (j->>'sim')::float sim
                    from jsonb_array_elements(cast(:j as jsonb)) j) x where e.id = x.id"""), {"j": json.dumps(ch), "now": now})
            c.execute(text("""
              update entity_metrics m set youtube_subscribers = x.subs,
                 signal_validity = coalesce(m.signal_validity,'{}'::jsonb) || jsonb_build_object('youtube', x.verdict,
                     'youtube_detail', jsonb_build_object('verdict', x.verdict, 'channel_id', x.cid, 'title', x.title, 'similarity', x.sim,
                                                          'subscribers', x.subs, 'id_source', x.url)),
                 signal_provenance = coalesce(m.signal_provenance,'{}'::jsonb) || jsonb_build_object('youtube_subscribers',
                     jsonb_build_object('source','youtube-data-api','channel_id', x.cid,'retrieved', cast(:now as text),'total_views', x.views,'via', x.verdict))
              from (select (j->>'id')::uuid id, (j->>'t')::timestamptz t, j->>'channel_id' cid, j->>'verdict' verdict, j->>'url' url, j->>'title' title,
                           (j->>'sim')::float sim, (j->>'subs')::bigint subs, (j->>'views')::bigint views
                    from jsonb_array_elements(cast(:j as jsonb)) j) x where m.entity_id = x.id and m.time = x.t"""), {"j": json.dumps(ch), "now": now})
    print("applied", len(res))


if __name__ == "__main__":
    main()

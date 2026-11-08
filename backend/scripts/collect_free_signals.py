"""
Phase 2 — free, keyless attention signals for ALL active entities with a Wikidata QID, stored in entity_metrics.

  wiki    : Wikimedia REST pageviews (user traffic, all-access) for the entity's en.wikipedia and hi.wikipedia
            articles (taken from Wikidata sitelinks): sum over the trailing 30 / 7 complete UTC days ->
            wikipedia_views_30d / _7d. NULL (not 0) when the entity has no such article.
  social  : Wikidata dated follower counts. P8687 statements (qualifier P2003 = Instagram, P6552/P2002 = Twitter/X)
            and P3744 qualifiers on P2003/P2002 claims. The newest statement is used ONLY if its point-in-time (P585)
            is within MAX_AGE_DAYS; the as-of date is stored in signal_provenance (these are not live counts).
  youtube : YouTube Data API channel stats for entities having external_ids.youtube_channel_id (stops on quota/429).

Spotify popularity/followers are NOT collected: the configured Spotify app now gets artist objects without
`popularity`/`followers`/`genres` (API change for dev-mode apps), so there is nothing real to store.

Writes: UPDATE the entity's newest entity_metrics row (composite_score is never touched); if the entity has no
metrics row, INSERT one (collection_source='free_signals') with a composite from compute_composite over the
signals it has. Small transactions with retry/backoff. Idempotent (newest values overwrite).

Usage: python scripts/collect_free_signals.py [--steps wiki,social,youtube] [--limit N] [--dry-run]
"""
import argparse
import asyncio
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
import requests
from sqlalchemy import create_engine, text

from app.core.config import settings

MAX_AGE_DAYS = 3 * 365
PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{proj}/all-access/user/{title}/daily/{s}/{e}"


def pageviews(proj, title, days=30):
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    url = PV.format(proj=proj, title=quote(title.replace(" ", "_"), safe=""), s=start.strftime("%Y%m%d"), e=end.strftime("%Y%m%d"))
    r = _wd.get(url, min_gap=0.12, timeout=30)
    if r is None:
        return None
    items = r.json().get("items", [])
    by_day = {i["timestamp"][:8]: i["views"] for i in items}
    d30 = sum(by_day.values())
    cut7 = (end - timedelta(days=6)).strftime("%Y%m%d")
    d7 = sum(v for k, v in by_day.items() if k >= cut7)
    return d30, d7


def sitelinks(qids):
    out = {}
    for i in range(0, len(qids), 50):
        r = _wd.get(_wd.WD_API, dict(action="wbgetentities", ids="|".join(qids[i:i + 50]), props="sitelinks", format="json"))
        if r:
            for q, e in r.json().get("entities", {}).items():
                s = e.get("sitelinks", {})
                out[q] = {"en": (s.get("enwiki") or {}).get("title"), "hi": (s.get("hiwiki") or {}).get("title")}
    return out


def social(qids):
    """qid -> {'instagram': (n, asof), 'twitter': (n, asof)} newest dated statements."""
    res = {}
    cutoff = (date.today() - timedelta(days=MAX_AGE_DAYS)).isoformat()
    for i in range(0, len(qids), 50):
        r = _wd.get(_wd.WD_API, dict(action="wbgetentities", ids="|".join(qids[i:i + 50]), props="claims", format="json"))
        if not r:
            continue
        for q, e in r.json().get("entities", {}).items():
            cl = e.get("claims", {})
            found = {}

            def take(plat, amount, qual):
                t = (qual.get("P585") or [{}])[0].get("datavalue", {}).get("value", {}).get("time")
                if not t:
                    return
                d = t[1:11]
                if d < cutoff:
                    return
                if plat not in found or d > found[plat][1]:
                    found[plat] = (int(float(amount)), d)
            for c in cl.get("P8687", []):
                sn = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                if not isinstance(sn, dict) or "amount" not in sn:
                    continue
                qual = c.get("qualifiers", {})
                if "P2003" in qual:
                    take("instagram", sn["amount"], qual)
                elif "P6552" in qual or "P2002" in qual:
                    take("twitter", sn["amount"], qual)
            for pid, plat in (("P2003", "instagram"), ("P2002", "twitter")):
                for c in cl.get(pid, []):
                    qual = c.get("qualifiers", {})
                    for n in qual.get("P3744", []):
                        v = (n.get("datavalue") or {}).get("value")
                        if isinstance(v, dict) and "amount" in v:
                            take(plat, v["amount"], qual)
            if found:
                res[q] = found
    return res


COLS = ["wikipedia_views_30d", "wikipedia_views_7d", "instagram_followers", "twitter_followers", "youtube_subscribers"]


def _retry(fn, what):
    for attempt in range(5):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001  Neon stalls (~60s) happen
            print("db retry", what, attempt + 1, type(exc).__name__, flush=True)
            time.sleep(10 * (attempt + 1))
    print("GAVE UP", what, flush=True)


def write_rows(eng, rows, dry):
    """rows: list of (entity_id, {col: val}, prov). Set-based: 1 read + 1 UPDATE (+1 INSERT) per chunk of 100
    entities, so ~3 round trips per 100 rows instead of 2 per row. Never touches composite_score on existing rows."""
    from app.services.scoring.composite import compute_composite
    if dry:
        return
    for i in range(0, len(rows), 100):
        chunk = rows[i:i + 100]
        ids = [str(r[0]) for r in chunk]

        def work(chunk=chunk, ids=ids):
            with eng.begin() as c:
                lat = {str(r[0]): r[1] for r in c.execute(text(
                    "select distinct on (entity_id) entity_id, time from entity_metrics where entity_id = any(CAST(:ids AS uuid[])) "
                    "order by entity_id, time desc"), {"ids": ids})}
                upd, ins = [], []
                for eid, cols, prov in chunk:
                    rec = {k: cols.get(k) for k in COLS}
                    rec["prov"] = prov
                    if str(eid) in lat:
                        upd.append({"eid": str(eid), "t": lat[str(eid)].isoformat(), **rec})
                    else:
                        comp, _ = compute_composite({"youtube_subscribers": cols.get("youtube_subscribers"),
                                                     "wikipedia_views_30d": cols.get("wikipedia_views_30d")})
                        ins.append({"eid": str(eid), "t": datetime.now(timezone.utc).isoformat(), "comp": comp, **rec})
                if upd:
                    c.execute(text("""update entity_metrics m set
                        wikipedia_views_30d = coalesce(v.wikipedia_views_30d, m.wikipedia_views_30d),
                        wikipedia_views_7d = coalesce(v.wikipedia_views_7d, m.wikipedia_views_7d),
                        instagram_followers = coalesce(v.instagram_followers, m.instagram_followers),
                        twitter_followers = coalesce(v.twitter_followers, m.twitter_followers),
                        youtube_subscribers = coalesce(v.youtube_subscribers, m.youtube_subscribers),
                        signal_provenance = coalesce(m.signal_provenance, '{}'::jsonb) || coalesce(v.prov, '{}'::jsonb)
                        from jsonb_to_recordset(CAST(:j AS jsonb)) as v(eid uuid, t timestamptz, wikipedia_views_30d bigint,
                          wikipedia_views_7d bigint, instagram_followers bigint, twitter_followers bigint, youtube_subscribers bigint, prov jsonb)
                        where m.entity_id = v.eid and m.time = v.t"""), {"j": json.dumps(upd)})
                if ins:
                    c.execute(text("""insert into entity_metrics (entity_id, time, wikipedia_views_30d, wikipedia_views_7d, instagram_followers,
                        twitter_followers, youtube_subscribers, composite_score, data_completeness, collection_source, signal_provenance)
                        select v.eid, v.t, v.wikipedia_views_30d, v.wikipedia_views_7d, v.instagram_followers, v.twitter_followers,
                          v.youtube_subscribers, v.comp, 0, 'free_signals', v.prov
                        from jsonb_to_recordset(CAST(:j AS jsonb)) as v(eid uuid, t timestamptz, wikipedia_views_30d bigint,
                          wikipedia_views_7d bigint, instagram_followers bigint, twitter_followers bigint, youtube_subscribers bigint,
                          comp float8, prov jsonb)"""), {"j": json.dumps(ins)})
            print(f"wrote chunk {i // 100 + 1}", flush=True)
        _retry(work, f"chunk{i}")


async def youtube_stats(items):
    from app.services.ingestion.youtube_client import YouTubeClient
    out, sem = {}, asyncio.Semaphore(3)
    blocked = False

    async def one(eid, ch):
        nonlocal blocked
        if blocked:
            return
        async with sem:
            try:
                async with YouTubeClient() as c:
                    st = await c.get_channel_stats(ch)
                if st and st.get("subscribers") is not None:
                    out[eid] = (int(st["subscribers"]), ch)
            except Exception as exc:  # noqa: BLE001
                if "429" in str(exc) or "403" in str(exc) or "quota" in str(exc).lower():
                    blocked = True
                    print("YouTube quota/429 -> stopping youtube step", flush=True)
    await asyncio.gather(*[one(e, c) for e, c in items])
    return out, blocked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", default="wiki,social,youtube")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    steps = set(a.steps.split(","))
    eng = create_engine(settings.POSTGRES_SYNC_URL, pool_pre_ping=True, connect_args={"connect_timeout": 20})
    with eng.connect() as c:
        ents = [dict(r) for r in c.execute(text("select id,name,external_ids->>'wikidata_qid' q, external_ids->>'youtube_channel_id' yt "
                                                "from entities where status='active' order by name")).mappings()]
    if a.limit:
        ents = ents[:a.limit]
    today = _wd.TODAY
    rows = {}  # eid -> [cols, prov]

    def slot(eid):
        return rows.setdefault(eid, [{}, {}])

    q_ents = [e for e in ents if e["q"]]
    if "wiki" in steps:
        sl = _wd.cached("sitelinks_en_hi_" + today, lambda: sitelinks([e["q"] for e in q_ents]))
        n = 0
        pv_cache = _wd.cached("pv_" + today + "_partial", lambda: {})
        for e in q_ents:
            s = sl.get(e["q"], {})
            tot30 = tot7 = 0; used = []
            for proj, key in (("en.wikipedia", "en"), ("hi.wikipedia", "hi")):
                t = s.get(key)
                if not t:
                    continue
                pv = pageviews(proj, t)
                if pv:
                    tot30 += pv[0]; tot7 += pv[1]; used.append(f"{proj}:{t}")
            if used:
                cols, prov = slot(e["id"])
                cols.update(wikipedia_views_30d=tot30, wikipedia_views_7d=tot7)
                prov["wikipedia_views"] = {"source": "wikimedia-rest-pageviews", "retrieved": today, "articles": used,
                                           "window_days": 30, "agent": "user", "access": "all-access"}
                n += 1
        print("wiki: entities with pageviews", n, "of", len(q_ents), flush=True)
    if "social" in steps:
        so = _wd.cached("social_" + today, lambda: social([e["q"] for e in q_ents]))
        n = 0
        for e in q_ents:
            f = so.get(e["q"])
            if not f:
                continue
            cols, prov = slot(e["id"])
            for plat, col in (("instagram", "instagram_followers"), ("twitter", "twitter_followers")):
                if plat in f:
                    cols[col] = f[plat][0]
                    prov[col] = {"source": "wikidata", "wikidata_qid": e["q"], "as_of": f[plat][1], "retrieved": today,
                                 "note": "dated statement, not a live count"}
            n += 1
        print("social: entities with fresh dated follower counts", n, flush=True)
    if "youtube" in steps:
        items = [(e["id"], e["yt"]) for e in ents if e["yt"]]
        res, blocked = asyncio.run(youtube_stats(items))
        for eid, (subs, ch) in res.items():
            cols, prov = slot(eid)
            cols["youtube_subscribers"] = subs
            prov["youtube_subscribers"] = {"source": "youtube-data-api", "channel_id": ch, "retrieved": today}
        print("youtube: channels fetched", len(res), "of", len(items), "(blocked)" if blocked else "", flush=True)
    todo = [(eid, v[0], v[1]) for eid, v in rows.items() if v[0]]
    print("entities to write:", len(todo), flush=True)
    write_rows(eng, todo, a.dry_run)
    print("done" + (" (dry-run)" if a.dry_run else ""), flush=True)


if __name__ == "__main__":
    main()

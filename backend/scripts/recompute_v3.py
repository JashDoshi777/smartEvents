"""Re-score EVERY entity_metrics row with composite v3 (app/services/scoring/composite.py).

History-consistent: identity-dependent verdicts (youtube / lastfm / wiki) come from each entity's LATEST non-null
signal_validity (identity does not change over time), so deltas between snapshots stay comparable; per-row data
(trends basis, news confidence, values) decides availability. Rows where the v3 rule fails get composite_score NULL
('unrated', score_version 'v3'). Social-listening-only rows (no signal columns) are left untouched.

Safety: dry-run by default. --apply first writes a backup CSV of the old composite_score/score_version/... for every row it
will change to the scratchpad, then batch-updates (500 rows per statement). Idempotent.
    python scripts/recompute_v3.py            # dry run: counts + sample
    python scripts/recompute_v3.py --apply
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, ".")
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.scoring.composite import SCORE_VERSION, compute_composite_v3

SCRATCH = "/private/tmp/claude-501/-Users-jash-doshi-zomato-com-Desktop-event/9552e9da-2773-47bc-b57e-03c883fcc8dc/scratchpad"
SIGNAL_COLS = ["lastfm_listeners", "youtube_subscribers", "wikipedia_views_30d", "google_trend_relative", "news_mentions_7d",
               "google_trend_score", "spotify_popularity"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        ents = {r["id"]: r["entity_type"] for r in c.execute(text("select id::text id, entity_type from entities")).mappings()}
        validity = {r["id"]: r["sv"] for r in c.execute(text(
            "select distinct on (entity_id) entity_id::text id, signal_validity sv from entity_metrics "
            "where signal_validity is not null order by entity_id, time desc")).mappings()}
        rows = c.execute(text(
            "select entity_id::text id, time, composite_score, score_version, score_confidence, signals_used, "
            "lastfm_listeners, youtube_subscribers, wikipedia_views_30d, google_trend_relative, google_trend_basis, "
            "news_mentions_7d, news_confidence, google_trend_score, spotify_popularity from entity_metrics order by entity_id, time")).mappings().all()
    print(len(rows), "metric rows;", len(validity), "entities with signal_validity")
    ups, cnt, skipped = [], Counter(), 0
    # Signals are collected by different jobs on different rows (the newest row often holds only Wikipedia/Trends), so each
    # row is scored on the LAST OBSERVED value of every signal at or before its time (as-of carry-forward of real values;
    # nothing from the future leaks into older rows). Trends and news carry their basis/confidence with the value.
    last, cur_id = {}, None
    for r in rows:
        if r["id"] != cur_id:
            cur_id, last = r["id"], {}
        if all(r[k] is None for k in SIGNAL_COLS):
            skipped += 1
            continue
        for k in ("lastfm_listeners", "youtube_subscribers", "wikipedia_views_30d"):
            if r[k] is not None:
                last[k] = r[k]
        if r["google_trend_relative"] is not None:
            last["trend"] = (r["google_trend_relative"], r["google_trend_basis"])
        if r["news_mentions_7d"] is not None and r["news_confidence"] is not None:
            last["news"] = (r["news_mentions_7d"], r["news_confidence"])
        m = {k: last.get(k) for k in ("lastfm_listeners", "youtube_subscribers", "wikipedia_views_30d")}
        m["google_trend_relative"], m["google_trend_basis"] = last.get("trend", (None, None))
        m["news_mentions_7d"], m["news_confidence"] = last.get("news", (None, None))
        res = compute_composite_v3(ents.get(r["id"]), m, validity.get(r["id"]))
        cnt["scored" if res["score"] is not None else "unrated"] += 1
        old = r["composite_score"]
        if (r["score_version"] == SCORE_VERSION and old == res["score"] and r["score_confidence"] == res["confidence"]
                and r["signals_used"] == res["signals_used"]):
            continue
        ups.append((r, res))
    print("social-only rows skipped:", skipped, "| v3 outcome:", dict(cnt), "| rows to change:", len(ups))
    for r, res in ups[:8]:
        print("  ", r["id"][:8], r["time"].date(), r["composite_score"], "->", res["score"], res["confidence"], res["signals_used"])
    if not a.apply:
        print("dry-run (use --apply). Backup CSV is written on --apply.")
        return
    bk = os.path.join(SCRATCH, f"composite_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.csv")
    with open(bk, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entity_id", "time", "composite_score", "score_version", "score_confidence", "signals_used"])
        for r, _ in ups:
            w.writerow([r["id"], r["time"].isoformat(), r["composite_score"], r["score_version"], r["score_confidence"],
                        json.dumps(r["signals_used"])])
    print("backup written:", bk)
    with eng.begin() as c:
        for i in range(0, len(ups), 500):
            payload = [{"id": r["id"], "t": r["time"].isoformat(), "s": res["score"], "c": res["confidence"],
                        "u": res["signals_used"]} for r, res in ups[i:i + 500]]
            c.execute(text("""update entity_metrics m set composite_score = x.s, score_confidence = x.c, signals_used = x.u,
                                 score_version = :v
                              from (select (j->>'id')::uuid id, (j->>'t')::timestamptz t, (j->>'s')::float s, (j->>'c')::float c, j->'u' u
                                    from jsonb_array_elements(cast(:j as jsonb)) j) x
                              where m.entity_id = x.id and m.time = x.t"""), {"j": json.dumps(payload), "v": SCORE_VERSION})
    print("applied", len(ups))


if __name__ == "__main__":
    main()

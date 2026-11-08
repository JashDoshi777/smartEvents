"""
Phase D — link existing events to a city / venue ONLY where the stored data gives evidence.

Evidence accepted (nothing is guessed):
  * city  : the event title carries an explicit city token, i.e. "<title> | <City>", "<title> - <City>" or
            "<title>, <City>" where <City> is a known city spelling (scraped_event_upsert.CITY_CANONICAL or a
            tracked city name).
  * city (alt): the District booking-URL slug contains exactly one known city token (e.g. ...-mumbai-2026-...)
  * venue : the event title contains the full name (>=8 chars, normalised) of exactly ONE venue and that
            venue is in the evidenced city (or no city evidenced but the name is unique across all venues).
PredictHQ rows carry no location in our table (client returned lat/lng but it was never persisted) and no
PredictHQ API key is configured, so they stay unlinked (reported). Re-running the District scraper / Ticketmaster
sync now persists city + venue_name_raw going forward.

Usage: python scripts/backfill_event_locations.py [--dry-run]
"""
import re
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.services.ingestion.scraped_event_upsert import CITY_CANONICAL


def main():
    dry = "--dry-run" in sys.argv
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        cities = [r[0] for r in c.execute(text("select name from cities"))]
        venues = [dict(r) for r in c.execute(text("select id,name,city from venues")).mappings()]
        evs = [dict(r) for r in c.execute(text("select id,title,source,city,venue_id,booking_url from events where venue_id is null or city is null")).mappings()]
    tokens = {n.lower(): n for n in cities}
    tokens.update({k: v for k, v in CITY_CANONICAL.items()})
    tokens["delhi ncr"] = "Delhi NCR"
    vn = [(_wd.norm(v["name"]), v) for v in venues if len(_wd.norm(v["name"])) >= 8]
    upd_city, upd_venue, unresolved = [], [], 0
    for e in evs:
        t = e["title"]
        city = e["city"]
        if not city:
            parts = [p.strip().lower() for p in re.split(r"\s[|\-–]\s|,\s", t)]
            hits = [tokens[p] for p in parts[1:] if p in tokens]
            if len(set(hits)) == 1:
                city = hits[0]; upd_city.append((e["id"], city))
        if not city and e.get("booking_url") and "district.in/events/" in e["booking_url"]:
            slug = e["booking_url"].split("/events/")[1].split("?")[0].lower().split("-")
            grams = set(slug) | {" ".join(slug[i:i + 2]) for i in range(len(slug) - 1)}
            hits = {tokens[g] for g in grams if g in tokens}
            if len(hits) == 1:
                city = hits.pop(); upd_city.append((e["id"], city))
        if not e["venue_id"]:
            nt = _wd.norm(t)
            ms = [v for n, v in vn if n in nt and (city is None or v["city"] == city)]
            if len(ms) == 1:
                upd_venue.append((e["id"], ms[0]["id"], ms[0]["name"], t))
        if not city and not e["venue_id"]:
            unresolved += 1
    print(f"events scanned {len(evs)}; city evidenced {len(upd_city)}; venue evidenced {len(upd_venue)}; no evidence {unresolved}")
    for x in upd_venue:
        print("  venue link:", x[3][:70], "->", x[2])
    if dry:
        return
    with eng.begin() as c:
        for eid, city in upd_city:
            c.execute(text("update events set city=:c where id=:i and city is null"), {"c": city, "i": eid})
        for eid, vid, _, _ in upd_venue:
            c.execute(text("update events set venue_id=:v where id=:i and venue_id is null"), {"v": vid, "i": eid})
    print("written")


if __name__ == "__main__":
    main()

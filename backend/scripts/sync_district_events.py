"""
Scrape district.in public event listings (existing Playwright scraper) for the tracked cities, one city at a time,
and upsert via scraped_event_upsert (idempotent on external_id+source; city + raw venue name persisted; venue_id only
on an unambiguous match to our venues table).
Usage: python scripts/sync_district_events.py [--cities "Mumbai,Pune"] [--max-events 40] [--pause 8]
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")
from app.services.ingestion.district_scraper import CITY_SEARCH_TERMS, scrape_city
from app.services.ingestion.scraped_event_upsert import upsert_scraped_events


def corroborated(ev, city):
    """District does not list every city: for cities outside its 12 supported ones the page may silently show a
    neighbouring city's events. Keep an event only if its own text (title / venue line / URL slug) names the city."""
    blob = " ".join(str(ev.get(k) or "") for k in ("title", "venue_name", "venue_line", "booking_url")).lower().replace("-", " ")
    return city.lower() in blob


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities")
    ap.add_argument("--max-events", type=int, default=40)
    ap.add_argument("--pause", type=float, default=8)
    a = ap.parse_args()
    cities = [c.strip() for c in a.cities.split(",")] if a.cities else list(CITY_SEARCH_TERMS)
    tot = {}
    for c in cities:
        try:
            evs = await scrape_city(c, max_events=a.max_events)
        except Exception as exc:  # noqa: BLE001
            print("city failed", c, type(exc).__name__, str(exc)[:100], flush=True); evs = []
        if c not in CITY_SEARCH_TERMS:
            n0 = len(evs)
            evs = [e for e in evs if corroborated(e, c)]
            print(f"  {c}: kept {len(evs)}/{n0} city-corroborated events", flush=True)
        res = await upsert_scraped_events(evs) if evs else {}
        print(f"{c}: scraped {len(evs)} -> {res}", flush=True)
        for k, v in res.items():
            tot[k] = tot.get(k, 0) + v
        await asyncio.sleep(a.pause)
    print("TOTAL", tot, flush=True)


if __name__ == "__main__":
    asyncio.run(main())

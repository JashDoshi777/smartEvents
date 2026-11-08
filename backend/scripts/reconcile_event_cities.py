"""
Repair events.city / venue_id for district events scraped for cities District does not actually support
(it showed a neighbouring city's listing, so events were tagged with the requested city).
Rules (evidence only): text = title + venue_name_raw + booking-URL slug.
  * exactly one known city token in text  -> city = that city
  * else if the current city is one of District's 12 supported cities -> keep
  * else if the current city token appears in text -> keep
  * else -> NULL (unverifiable)
A venue link is cleared when the venue's city differs from the (reconciled) event city.
Usage: python scripts/reconcile_event_cities.py [--dry-run]
"""
import sys
sys.path.insert(0, ".")
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.services.ingestion.district_scraper import CITY_SEARCH_TERMS
from app.services.ingestion.scraped_event_upsert import CITY_CANONICAL


def main():
    dry = "--dry-run" in sys.argv
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        cities = [r[0] for r in c.execute(text("select name from cities"))]
        evs = [dict(r) for r in c.execute(text("select e.id,e.title,e.city,e.venue_name_raw,e.booking_url,e.venue_id,v.city vcity from events e left join venues v on v.id=e.venue_id where e.source='district'")).mappings()]
    toks = {n.lower(): n for n in cities}
    toks.update(CITY_CANONICAL)
    toks.pop("goa", None); toks["goa"] = "Goa"
    ups = []
    for e in evs:
        blob = " ".join(str(e.get(k) or "") for k in ("title", "venue_name_raw")) + " " + ((e["booking_url"] or "").split("/events/")[-1])
        words = " " + " ".join(blob.lower().replace("-", " ").replace("|", " ").replace(",", " ").split()) + " "
        hits = {v for k, v in toks.items() if f" {k} " in words}
        cur = e["city"]
        if len(hits) == 1:
            new = next(iter(hits))
        elif cur in CITY_SEARCH_TERMS or (cur and cur in hits):
            new = cur
        else:
            new = None
        clear_v = e["venue_id"] is not None and e["vcity"] is not None and new is not None and e["vcity"] != new
        if new != cur or clear_v:
            ups.append((e["id"], new, clear_v))
    print(f"district events {len(evs)}; to change {len(ups)}; venue links to clear {sum(1 for u in ups if u[2])}")
    if dry:
        return
    with eng.begin() as c:
        for i, n, cv in ups:
            c.execute(text("update events set city=:n" + (", venue_id=NULL" if cv else "") + " where id=:i"), {"n": n, "i": i})
    print("written")


if __name__ == "__main__":
    main()

"""
LiveIQ — Restaurant/Venue Sync Worker (Master Data)
Pulls real dining & nightlife venue listings — restaurants, cafes,
bars, and nightclubs — from Foursquare Places API and OpenStreetMap
(via Overpass) for each of the 12 tracked cities, and upserts into the
`restaurants` table (see app/models/restaurant.py for the naming note).

Foursquare is queried once per venue_type (4 category-scoped searches)
since its API takes a single category filter per call. Overpass is
queried ONCE per city covering all 5 amenity values via a regex-OR'd
query (see overpass_client.py) — no need to repeat that per type.

Cross-source matching: a venue appearing in BOTH sources near the same
coordinates (within MATCH_RADIUS_METERS) with a similar name is merged
into ONE row (both foursquare_place_id and osm_id populated). This is a
real proximity+fuzzy-name match, not a guess — venues that don't clear
both thresholds are kept as separate rows rather than force-merged,
since a wrong merge would misrepresent two different businesses as one.
Matching is also scoped to venues of the SAME venue_type — a restaurant
and an unrelated bar 50m apart must never merge just because they're
close, regardless of name similarity.

Schedule: every 24 hours (see celery_app.py beat_schedule) — venue
listings change far less often than events, so this doesn't need the
6-hour cadence used elsewhere.
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog
from celery import Task
from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.workers.celery_app import celery_app
from app.workers.run_utils import run_async
from app.services.ingestion.foursquare_client import FoursquareClient, CATEGORY_IDS as FOURSQUARE_VENUE_TYPES
from app.services.ingestion.overpass_client import OverpassClient
from app.core.database import AsyncSessionLocal
from app.models.restaurant import Restaurant

logger = structlog.get_logger()

# Real city-center coordinates for the 12 tracked cities (standard,
# widely-cited city-center lat/lng — a stable geographic fact, not
# something that needs a live API lookup or can be "wrong" the way a
# business's rating would be).
CITY_CENTERS: Dict[str, tuple[float, float]] = {
    "Mumbai": (19.0760, 72.8777),
    "Delhi NCR": (28.6139, 77.2090),
    "Bengaluru": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
    "Chennai": (13.0827, 80.2707),
    "Kolkata": (22.5726, 88.3639),
    "Ahmedabad": (23.0225, 72.5714),
    "Jaipur": (26.9124, 75.7873),
    "Chandigarh": (30.7333, 76.7794),
    "Kochi": (9.9312, 76.2673),
    "Indore": (22.7196, 75.8577),
    "Pune": (18.5204, 73.8567),
}

SEARCH_RADIUS_METERS = 5000
BBOX_DELTA_DEGREES = 0.05  # ~5km at these latitudes — matches SEARCH_RADIUS_METERS roughly
MATCH_RADIUS_METERS = 100  # real-world "this is probably the same building" threshold


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000  # Earth radius, meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _names_similar(a: str, b: str) -> bool:
    """
    Cheap, real similarity check — not a guess. Requires one name to
    contain the other (after lowercasing) OR share their first
    significant word, catching common cases like "Yauatcha" vs
    "Yauatcha Mumbai" without a heavier fuzzy-matching dependency.
    """
    a_low, b_low = a.lower().strip(), b.lower().strip()
    if a_low in b_low or b_low in a_low:
        return True
    a_first = a_low.split()[0] if a_low.split() else ""
    b_first = b_low.split()[0] if b_low.split() else ""
    return len(a_first) > 3 and a_first == b_first


def _merge_sources(
    foursquare_results: List[Dict[str, Any]],
    osm_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Real proximity + name matching, scoped to matching venue_type —
    a restaurant and a nearby-but-unrelated bar must never merge just
    because they're close and happen to share a word in their name.
    Every Foursquare result with NO close-enough, same-type,
    name-similar OSM match is kept as its own row (osm fields NULL);
    every OSM result not matched to a Foursquare result is likewise
    kept standalone. Matched pairs merge into one row with fields from
    both sources — Foursquare's venue_type wins on a match since it was
    the more specific category search that found it.
    """
    merged: List[Dict[str, Any]] = []
    used_osm_indices: set = set()

    for fsq in foursquare_results:
        if fsq["latitude"] is None or fsq["longitude"] is None:
            continue
        match_idx = None
        for i, osm in enumerate(osm_results):
            if i in used_osm_indices or osm["latitude"] is None or osm["longitude"] is None:
                continue
            if osm["venue_type"] != fsq["venue_type"]:
                continue
            dist = _haversine_meters(fsq["latitude"], fsq["longitude"], osm["latitude"], osm["longitude"])
            if dist <= MATCH_RADIUS_METERS and _names_similar(fsq["name"], osm["name"]):
                match_idx = i
                break

        if match_idx is not None:
            osm = osm_results[match_idx]
            used_osm_indices.add(match_idx)
            merged.append({
                "name": fsq["name"],
                "venue_type": fsq["venue_type"],
                "foursquare_place_id": fsq["foursquare_place_id"],
                "osm_id": osm["osm_id"],
                "osm_type": osm["osm_type"],
                "latitude": fsq["latitude"],
                "longitude": fsq["longitude"],
                "formatted_address": fsq["formatted_address"] or osm["address"],
                "foursquare_categories": fsq["categories"],
                "osm_cuisines": osm["cuisines"],
                "phone": fsq["phone"] or osm["phone"],
                "website": fsq["website"] or osm["website"],
                "opening_hours": osm["opening_hours"],
            })
        else:
            merged.append({
                "name": fsq["name"],
                "venue_type": fsq["venue_type"],
                "foursquare_place_id": fsq["foursquare_place_id"],
                "osm_id": None,
                "osm_type": None,
                "latitude": fsq["latitude"],
                "longitude": fsq["longitude"],
                "formatted_address": fsq["formatted_address"],
                "foursquare_categories": fsq["categories"],
                "osm_cuisines": [],
                "phone": fsq["phone"],
                "website": fsq["website"],
                "opening_hours": None,
            })

    for i, osm in enumerate(osm_results):
        if i in used_osm_indices or osm["latitude"] is None or osm["longitude"] is None:
            continue
        merged.append({
            "name": osm["name"],
            "venue_type": osm["venue_type"],
            "foursquare_place_id": None,
            "osm_id": osm["osm_id"],
            "osm_type": osm["osm_type"],
            "latitude": osm["latitude"],
            "longitude": osm["longitude"],
            "formatted_address": osm["address"],
            "foursquare_categories": [],
            "osm_cuisines": osm["cuisines"],
            "phone": osm["phone"],
            "website": osm["website"],
            "opening_hours": osm["opening_hours"],
        })

    return merged


async def _upsert_restaurants(city: str, records: List[Dict[str, Any]]) -> Dict[str, int]:
    inserted = 0
    updated = 0
    errors = 0
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        for rec in records:
            try:
                if rec["foursquare_place_id"]:
                    # Foursquare ID is a real unique key — upsert on it directly.
                    stmt = pg_insert(Restaurant).values(city=city, scraped_at=now, created_at=now, updated_at=now, **rec)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["foursquare_place_id"],
                        set_={
                            "name": rec["name"], "venue_type": rec["venue_type"],
                            "osm_id": rec["osm_id"], "osm_type": rec["osm_type"],
                            "formatted_address": rec["formatted_address"],
                            "foursquare_categories": rec["foursquare_categories"], "osm_cuisines": rec["osm_cuisines"],
                            "phone": rec["phone"], "website": rec["website"], "opening_hours": rec["opening_hours"],
                            "updated_at": now,
                        },
                    )
                elif rec["osm_id"] is not None:
                    stmt = pg_insert(Restaurant).values(city=city, scraped_at=now, created_at=now, updated_at=now, **rec)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_restaurant_osm",
                        set_={
                            "name": rec["name"], "venue_type": rec["venue_type"],
                            "formatted_address": rec["formatted_address"], "osm_cuisines": rec["osm_cuisines"],
                            "phone": rec["phone"], "website": rec["website"], "opening_hours": rec["opening_hours"],
                            "updated_at": now,
                        },
                    )
                else:
                    errors += 1
                    continue

                stmt = stmt.returning(literal_column("(xmax = 0)").label("was_inserted"))
                # Each row commits in its own transaction (rather than one
                # shared session.begin() for the whole city) — a real bug
                # surfaced in production data: one Kolkata venue's `phone`
                # tag exceeded the old VARCHAR(50) limit, and because all
                # rows shared one transaction, that single failure aborted
                # Postgres's transaction state for every row after it too
                # (asyncpg's InFailedSQLTransactionError), turning 1 real
                # bad row into 181 false "errors" for otherwise-good venues.
                async with session.begin():
                    result = await session.execute(stmt)
                    row = result.first()
                if row is not None and row.was_inserted:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                logger.warning("restaurant_sync: upsert error", error=str(exc), name=rec.get("name"))
                errors += 1

    return {"inserted": inserted, "updated": updated, "errors": errors}


async def _run_sync() -> Dict[str, Any]:
    total_merged = 0
    per_city: Dict[str, int] = {}

    for city, (lat, lng) in CITY_CENTERS.items():
        # Foursquare: one search call per venue_type (its API takes a
        # single category filter per request).
        fsq_results: List[Dict[str, Any]] = []
        async with FoursquareClient() as fsq_client:
            for venue_type in FOURSQUARE_VENUE_TYPES:
                try:
                    results = await fsq_client.search_venues_nearby(
                        lat, lng, venue_type=venue_type, radius_meters=SEARCH_RADIUS_METERS, limit=50
                    )
                    fsq_results.extend(results)
                except Exception as exc:
                    logger.warning("restaurant_sync: Foursquare fetch failed", city=city, venue_type=venue_type, error=str(exc))

        # Overpass: one call covers all amenity types at once (see
        # overpass_client.py's regex-OR'd query).
        try:
            async with OverpassClient() as osm_client:
                osm_results = await osm_client.search_venues_bbox(
                    south=lat - BBOX_DELTA_DEGREES, west=lng - BBOX_DELTA_DEGREES,
                    north=lat + BBOX_DELTA_DEGREES, east=lng + BBOX_DELTA_DEGREES,
                )
        except Exception as exc:
            logger.warning("restaurant_sync: Overpass fetch failed", city=city, error=str(exc))
            osm_results = []

        merged = _merge_sources(fsq_results, [r for r in osm_results if r is not None])
        db_result = await _upsert_restaurants(city, merged)
        per_city[city] = len(merged)
        total_merged += len(merged)
        logger.info("restaurant_sync: city complete", city=city, foursquare=len(fsq_results), osm=len([r for r in osm_results if r]), merged=len(merged), **db_result)

    return {
        "status": "ok",
        "total_merged": total_merged,
        "per_city": per_city,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(
    name="app.workers.restaurant_sync.sync_restaurants",
    bind=True,
    max_retries=3,
    default_retry_delay=600,
)
def sync_restaurants(self: Task):
    logger.info("restaurant_sync: starting sync cycle")
    try:
        result = run_async(_run_sync())
        logger.info("restaurant_sync: cycle complete", **result)
        return result
    except Exception as exc:
        logger.error("restaurant_sync: cycle failed", error=str(exc))
        raise self.retry(exc=exc)

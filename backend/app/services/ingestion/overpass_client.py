"""
LiveIQ — Overpass API Client (OpenStreetMap)
Real venue data: name, cuisine tags, address, opening hours. Covers
restaurants, cafes, bars, pubs, and nightclubs via OSM's `amenity` tag
— not just sit-down restaurants.
No API key needed — public, community-run Overpass instances.

Verified live against the current API before writing this client:
overpass-api.de is the primary public instance (no auth), `[out:json]`
is current syntax, no numeric rating field exists on OSM nodes (OSM is
a map database, not a review platform — never fabricate one).

Fair-use throttling: overpass-api.de's documented guidance is to stay
well under ~10,000 requests/day and 1GB/day, with per-IP concurrent
"slots" — the client here throttles to a real minimum delay between
calls and falls back to a community mirror on failure, per current
community-recommended practice (no official load balancer exists).
"""

import asyncio
import time
from typing import Any, Dict, List, Optional
import httpx
import structlog

logger = structlog.get_logger()

PRIMARY_ENDPOINT = "https://overpass-api.de/api/interpreter"
FALLBACK_ENDPOINT = "https://overpass.private.coffee/api/interpreter"
MIN_REQUEST_INTERVAL_SECONDS = 1.5  # conservative, well under fair-use limits
USER_AGENT = "LiveIQ-District-Intelligence/1.0 (research project; contact via backend .env maintainer)"


class OverpassClient:
    _last_request_at: float = 0.0

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        # Overpass's public instances are free, best-effort, and can be
        # genuinely slow under load (observed 500+ error and 30s+ hangs
        # during testing) — a longer client timeout than most of this
        # codebase's other API clients, not a bug, just this service's
        # real-world reliability profile.
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0), headers={"User-Agent": USER_AGENT})
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _throttle(self):
        elapsed = time.monotonic() - OverpassClient._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        OverpassClient._last_request_at = time.monotonic()

    async def _run_query(self, query: str) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("OverpassClient must be used as an async context manager")

        await self._throttle()
        for endpoint in (PRIMARY_ENDPOINT, FALLBACK_ENDPOINT):
            try:
                response = await self._client.post(endpoint, data={"data": query})
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                logger.warning("overpass_client: endpoint failed, trying next", endpoint=endpoint, error=str(exc))
                continue
        raise RuntimeError("Overpass query failed on both primary and fallback endpoints")

    # OSM's `amenity` tag values for the venue types this project tracks.
    # A single regex-OR'd query fetches all of them in one Overpass call
    # per city instead of 4 — friendlier to the fair-use limits than
    # firing 4x the requests for the same coverage.
    AMENITY_VALUES = ["restaurant", "cafe", "bar", "pub", "nightclub"]

    async def search_venues_bbox(
        self,
        south: float, west: float, north: float, east: float,
        timeout_seconds: int = 60,
    ) -> List[Dict[str, Any]]:
        """Restaurants, cafes, bars, pubs, and nightclubs within a bounding box — good for a whole city."""
        amenity_regex = "^(" + "|".join(self.AMENITY_VALUES) + ")$"
        query = f"""
[out:json][timeout:{timeout_seconds}];
(
  node["amenity"~"{amenity_regex}"]({south},{west},{north},{east});
  way["amenity"~"{amenity_regex}"]({south},{west},{north},{east});
);
out center tags;
""".strip()
        data = await self._run_query(query)
        return [self._normalize(el) for el in data.get("elements", [])]

    @staticmethod
    def _normalize(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tags = raw.get("tags", {})
        name = tags.get("name")
        if not name:
            return None  # unnamed OSM nodes aren't useful venue listings

        amenity = tags.get("amenity")
        # OSM's amenity=pub is functionally the same "bar" venue type this
        # project tracks — collapse it rather than add a 6th UI category
        # for a tag distinction (British "pub" vs "bar") that isn't
        # meaningful to a District/Zomato partnership use case.
        venue_type = "bar" if amenity == "pub" else amenity

        # 'node' elements have lat/lon directly; 'way' elements only have a
        # computed 'center' (from `out center`) — check both, never guess one.
        lat = raw.get("lat") or (raw.get("center") or {}).get("lat")
        lon = raw.get("lon") or (raw.get("center") or {}).get("lon")

        cuisine_raw = tags.get("cuisine")
        cuisines = [c.strip() for c in cuisine_raw.split(";")] if cuisine_raw else []

        return {
            "osm_id": raw.get("id"),
            "osm_type": raw.get("type"),
            "name": name,
            "venue_type": venue_type,
            "cuisines": cuisines,
            "latitude": lat,
            "longitude": lon,
            "address": tags.get("addr:full") or ", ".join(
                p for p in [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")] if p
            ) or None,
            "opening_hours": tags.get("opening_hours"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "rating": None,  # OSM has no rating field — never fabricated
        }

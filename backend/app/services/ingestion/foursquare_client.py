"""
LiveIQ — Foursquare Places API Client
Real venue data: name, address, category (cuisine-ish), phone, website,
lat/lng. Covers restaurants, cafes, bars, and nightclubs — not just
sit-down restaurants, since District/Zomato's real footprint spans
dining AND nightlife.

IMPORTANT — verified live against the current API before writing this
client (not from training-data memory): Foursquare's legacy Places API
v3 (api.foursquare.com/v3/...) was deprecated May 15, 2026. The current
API lives at a DIFFERENT host: places-api.foursquare.com, and requires
a dated `X-Places-Api-Version` header. Only the service API key
(FOURSQUARE_PLACES_API, sent as a Bearer token) is used — CLIENT_ID/
CLIENT_SECRET belong to a different, unrelated Foursquare product
(OAuth user-auth flows) and are not needed for place search.

Category IDs below are from Foursquare's public legacy taxonomy, which
the current Places API still keys `fsq_category_ids` against (no
`/categories` listing endpoint is available on this API tier — 404
confirmed live — so each ID was instead verified by a live search
returning real, correctly-categorized results before being used here).

`rating` exists on this API but is a Premium-tier field billed from the
first call with zero free quota — deliberately not requested here, so
this client only ever costs against the (cheaper/free-tier) Pro fields.
No fabricated rating is substituted in its place; venues from this
source simply have rating: None, same as any other missing-data case
in this codebase.
"""

from typing import Any, Dict, List, Optional
import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

FOURSQUARE_BASE_URL = "https://places-api.foursquare.com"
API_VERSION_HEADER = "2025-06-17"

# Verified live (see module docstring) — each returns real, correctly
# categorized results, not guessed IDs.
CATEGORY_IDS = {
    "restaurant": "4d4b7105d754a06374d81259",   # "Restaurant" parent category
    "cafe": "4bf58dd8d48988d16d941735",          # Cafe (includes Coffee Shop subtype in results)
    "bar": "4bf58dd8d48988d116941735",           # Bar
    "nightclub": "4bf58dd8d48988d11f941735",     # Night Club
}


class FoursquareClient:
    """
    Not a BaseAPIClient subclass — same reasoning as GooglePlacesClient:
    this API's header-based versioning (X-Places-Api-Version) and Bearer
    auth don't need BaseAPIClient's apikey-in-query-param GET pattern,
    and a thin dedicated wrapper is simpler than forcing the fit.
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=FOURSQUARE_BASE_URL, timeout=httpx.Timeout(15.0))
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> Dict[str, str]:
        if not settings.is_api_configured("foursquare"):
            raise RuntimeError(
                "Foursquare API not configured. Add FOURSQUARE_PLACES_API to .env"
            )
        return {
            "Authorization": f"Bearer {settings.FOURSQUARE_PLACES_API}",
            "X-Places-Api-Version": API_VERSION_HEADER,
        }

    async def search_venues_nearby(
        self,
        latitude: float,
        longitude: float,
        venue_type: str,
        radius_meters: int = 5000,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        if self._client is None:
            raise RuntimeError("FoursquareClient must be used as an async context manager")
        if venue_type not in CATEGORY_IDS:
            raise ValueError(f"Unknown venue_type '{venue_type}' — must be one of {list(CATEGORY_IDS)}")

        params = {
            "ll": f"{latitude},{longitude}",
            "radius": min(radius_meters, 100_000),
            "fsq_category_ids": CATEGORY_IDS[venue_type],
            "limit": min(limit, 50),
        }
        response = await self._client.get("/places/search", headers=self._headers(), params=params)
        response.raise_for_status()
        data = response.json()
        return [self._normalize(p, venue_type) for p in data.get("results", [])]

    @staticmethod
    def _normalize(raw: Dict[str, Any], venue_type: str) -> Dict[str, Any]:
        location = raw.get("location") or {}
        categories = raw.get("categories", [])
        return {
            "foursquare_place_id": raw.get("fsq_place_id"),
            "name": raw.get("name"),
            "venue_type": venue_type,
            "categories": [c.get("name") for c in categories if c.get("name")],
            "formatted_address": location.get("formatted_address"),
            "locality": location.get("locality"),
            "latitude": raw.get("latitude"),
            "longitude": raw.get("longitude"),
            "phone": raw.get("tel"),
            "website": raw.get("website"),
            "rating": None,  # deliberately not requested — see module docstring
            "price_level": None,  # not requested in this call (Pro/Premium split); left NULL, not guessed
        }

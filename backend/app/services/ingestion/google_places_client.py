"""
LiveIQ — Google Places API (New) Client
Real restaurant + venue data: name, rating, price level, cuisine-ish
"types", location, opening hours.

IMPORTANT: this targets Places API (New) — POST-based, header-authed
(X-Goog-Api-Key / X-Goog-FieldMask) — NOT the legacy GET-based
`maps.googleapis.com/maps/api/place/...` API. Google closed the legacy
API to new projects in March 2025; this project's key only works
against the New API. Verified live against current Google docs
(https://developers.google.com/maps/documentation/places/web-service/nearby-search)
before writing this client — do not "fix" this back to the legacy
GET/query-param shape, it will not work for a new API key.

FIELD MASK COST NOTE: rating/userRatingCount/priceLevel/currentOpeningHours
fall under Google's pricier "Nearby Search Enterprise" SKU tier vs. the
cheaper "Pro" tier for displayName/primaryType/formattedAddress/location.
Only request what's actually used to avoid unnecessary SKU-tier cost.
"""

from typing import Any, Dict, List, Optional
import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

PLACES_BASE_URL = "https://places.googleapis.com/v1"

# Restaurant-relevant field mask — every field here is used by the
# normalizer below; don't add fields "just in case," they cost more.
RESTAURANT_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.rating",
    "places.userRatingCount",
    "places.priceLevel",
    "places.primaryType",
    "places.types",
    "places.formattedAddress",
    "places.location",
    "places.currentOpeningHours",
])


class GooglePlacesClient:
    """
    Not a BaseAPIClient subclass — Places API (New) uses POST + custom
    headers (X-Goog-*) rather than the api-key-in-query-param GET
    pattern BaseAPIClient's retry/circuit-breaker logic was built around
    for the other (GET-based) clients in this codebase. A thin, dedicated
    httpx wrapper here is simpler and more honest than forcing a
    POST+header-auth API through a base class shaped for GET+query auth.
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=PLACES_BASE_URL, timeout=httpx.Timeout(15.0))
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _api_key(self) -> str:
        if not settings.is_api_configured("google_places"):
            raise RuntimeError(
                "Google Places API not configured. Add GOOGLE_PLACES_API_KEY to .env"
            )
        return settings.GOOGLE_PLACES_API_KEY

    async def search_restaurants_nearby(
        self,
        latitude: float,
        longitude: float,
        radius_meters: float = 5000.0,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        if self._client is None:
            raise RuntimeError("GooglePlacesClient must be used as an async context manager")

        body = {
            "includedTypes": ["restaurant"],
            "maxResultCount": min(max_results, 20),  # API hard cap is 20 per request
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_meters,
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key(),
            "X-Goog-FieldMask": RESTAURANT_FIELD_MASK,
        }

        response = await self._client.post("/places:searchNearby", json=body, headers=headers)
        response.raise_for_status()
        data = response.json()
        return [self._normalize_restaurant(p) for p in data.get("places", [])]

    @staticmethod
    def _normalize_restaurant(raw: Dict[str, Any]) -> Dict[str, Any]:
        display_name = raw.get("displayName") or {}
        opening_hours = raw.get("currentOpeningHours") or {}
        return {
            "google_place_id": raw.get("id"),
            "name": display_name.get("text"),
            "rating": raw.get("rating"),
            "user_rating_count": raw.get("userRatingCount"),
            # priceLevel is an enum string like "PRICE_LEVEL_MODERATE" in the
            # New API (not a 0-4 int like legacy) — kept as the raw enum
            # string; callers that need a number should map it explicitly
            # rather than this client guessing an int mapping.
            "price_level": raw.get("priceLevel"),
            "primary_type": raw.get("primaryType"),
            "types": raw.get("types", []),
            "formatted_address": raw.get("formattedAddress"),
            "latitude": (raw.get("location") or {}).get("latitude"),
            "longitude": (raw.get("location") or {}).get("longitude"),
            "open_now": opening_hours.get("openNow"),
        }

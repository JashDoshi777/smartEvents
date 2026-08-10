"""
LiveIQ — Ticketmaster Discovery API Client
Data collected:
  - Events search for India and global Indian artists
  - Event details: venue, date, ticket prices, capacity, status
  - Venue details: location, capacity
  - Attractions (artists): popularity, social links
"""

from typing import Any, Dict, List, Optional
import structlog

from app.services.ingestion.base_client import BaseAPIClient
from app.core.config import settings

logger = structlog.get_logger()


class TicketmasterClient(BaseAPIClient):
    BASE_URL = "https://app.ticketmaster.com/discovery/v2"
    RATE_LIMIT = 5      # 5,000 req/day on free tier — be conservative
    TIMEOUT = 10.0

    def _api_key(self) -> str:
        if not settings.is_api_configured("ticketmaster"):
            raise RuntimeError(
                "Ticketmaster API not configured. Add TICKETMASTER_API_KEY to .env"
            )
        return settings.TICKETMASTER_API_KEY

    # ─── Events ────────────────────────────────────────────────────────────────

    async def search_events(
        self,
        keyword: Optional[str] = None,
        country_code: str = "IN",
        city: Optional[str] = None,
        classification_name: Optional[str] = None,  # 'Music', 'Sports', 'Comedy'
        size: int = 20,
        page: int = 0,
        sort: str = "date,asc",
    ) -> Dict[str, Any]:
        """
        Search events in India.
        Returns paginated events with venue and price info.
        """
        params: Dict[str, Any] = {
            "apikey": self._api_key(),
            "countryCode": country_code,
            "size": min(size, 200),
            "page": page,
            "sort": sort,
        }
        if keyword:
            params["keyword"] = keyword
        if city:
            params["city"] = city
        if classification_name:
            params["classificationName"] = classification_name

        data = await self.get("/events.json", params=params)
        embedded = data.get("_embedded", {})
        page_info = data.get("page", {})

        return {
            "events": [self._normalize_event(e) for e in embedded.get("events", [])],
            "total_elements": page_info.get("totalElements", 0),
            "total_pages": page_info.get("totalPages", 0),
            "current_page": page_info.get("number", 0),
        }

    async def get_event(self, event_id: str) -> Dict[str, Any]:
        """Get full event details by Ticketmaster event ID."""
        data = await self.get(f"/events/{event_id}.json", params={"apikey": self._api_key()})
        return self._normalize_event(data)

    async def search_attractions(
        self,
        keyword: str,
        classification_name: Optional[str] = None,
        size: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search artists/attractions by name.
        An "attraction" in Ticketmaster = an artist or sports team.
        """
        params: Dict[str, Any] = {
            "apikey": self._api_key(),
            "keyword": keyword,
            "size": size,
        }
        if classification_name:
            params["classificationName"] = classification_name

        data = await self.get("/attractions.json", params=params)
        embedded = data.get("_embedded", {})
        return [
            self._normalize_attraction(a)
            for a in embedded.get("attractions", [])
        ]

    async def search_venues(
        self,
        keyword: Optional[str] = None,
        country_code: str = "IN",
        city: Optional[str] = None,
        size: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search venues in India."""
        params: Dict[str, Any] = {
            "apikey": self._api_key(),
            "countryCode": country_code,
            "size": size,
        }
        if keyword:
            params["keyword"] = keyword
        if city:
            params["city"] = city

        data = await self.get("/venues.json", params=params)
        embedded = data.get("_embedded", {})
        return [self._normalize_venue(v) for v in embedded.get("venues", [])]

    # ─── Normalization ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_event(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten Ticketmaster event to LiveIQ format."""
        dates = raw.get("dates", {}).get("start", {})
        embedded = raw.get("_embedded", {})
        venues = embedded.get("venues", [{}])
        attractions = embedded.get("attractions", [{}])
        price_ranges = raw.get("priceRanges", [])
        ticket_limit = raw.get("ticketLimit", {})
        sales = raw.get("sales", {}).get("public", {})
        classifications = raw.get("classifications", [{}])

        return {
            "ticketmaster_id": raw.get("id"),
            "name": raw.get("name"),
            "status": raw.get("dates", {}).get("status", {}).get("code"),  # 'onsale', 'offsale', 'cancelled'
            "event_date": dates.get("dateTime"),          # ISO8601
            "event_date_local": dates.get("localDate"),
            "event_time_local": dates.get("localTime"),
            "timezone": raw.get("dates", {}).get("timezone"),
            "is_tbd": dates.get("dateTBD", False),
            "venue": TicketmasterClient._normalize_venue(venues[0]) if venues else None,
            "attraction": TicketmasterClient._normalize_attraction(attractions[0]) if attractions else None,
            "price_min": price_ranges[0].get("min") if price_ranges else None,
            "price_max": price_ranges[0].get("max") if price_ranges else None,
            "price_currency": price_ranges[0].get("currency", "INR") if price_ranges else "INR",
            "sales_start": sales.get("startDateTime"),
            "sales_end": sales.get("endDateTime"),
            "classification_segment": classifications[0].get("segment", {}).get("name"),
            "classification_genre": classifications[0].get("genre", {}).get("name"),
            "classification_sub_genre": classifications[0].get("subGenre", {}).get("name"),
            "ticket_limit_info": ticket_limit.get("info"),
            "ticket_url": raw.get("url"),
            "cover_image": (
                sorted(raw.get("images", []), key=lambda x: x.get("width", 0), reverse=True)[0].get("url")
                if raw.get("images") else None
            ),
        }

    @staticmethod
    def _normalize_venue(raw: Dict[str, Any]) -> Dict[str, Any]:
        location = raw.get("location", {})
        city = raw.get("city", {})
        state = raw.get("state", {})
        country = raw.get("country", {})
        return {
            "ticketmaster_venue_id": raw.get("id"),
            "name": raw.get("name"),
            "address": raw.get("address", {}).get("line1"),
            "city": city.get("name"),
            "state": state.get("name"),
            "country": country.get("name"),
            "country_code": country.get("countryCode"),
            "postal_code": raw.get("postalCode"),
            "latitude": float(location.get("latitude", 0)) or None,
            "longitude": float(location.get("longitude", 0)) or None,
            "timezone": raw.get("timezone"),
            "capacity": raw.get("generalInfo", {}).get("generalRule"),
            "url": raw.get("url"),
        }

    @staticmethod
    def _normalize_attraction(raw: Dict[str, Any]) -> Dict[str, Any]:
        images = sorted(raw.get("images", []), key=lambda x: x.get("width", 0), reverse=True)
        classifications = raw.get("classifications", [{}])
        external_links = raw.get("externalLinks", {})
        return {
            "ticketmaster_attraction_id": raw.get("id"),
            "name": raw.get("name"),
            "segment": classifications[0].get("segment", {}).get("name") if classifications else None,
            "genre": classifications[0].get("genre", {}).get("name") if classifications else None,
            "spotify_url": (external_links.get("spotify", [{}])[0].get("url") if external_links.get("spotify") else None),
            "instagram_url": (external_links.get("instagram", [{}])[0].get("url") if external_links.get("instagram") else None),
            "twitter_url": (external_links.get("twitter", [{}])[0].get("url") if external_links.get("twitter") else None),
            "youtube_url": (external_links.get("youtube", [{}])[0].get("url") if external_links.get("youtube") else None),
            "image_url": images[0].get("url") if images else None,
            "url": raw.get("url"),
        }

"""
LiveIQ — PredictHQ API Client
Real demand-intelligence signals for events: `rank`/`local_rank` (0-100
event significance scores) and `phq_attendance` (predicted attendance
integer) — genuine external signals that no other source in this
codebase provides, used to strengthen the fill-rate ML model and
cross-validate District/BookMyShow scraped events.

Docs verified live (not from training-data memory) before writing this
client: https://docs.predicthq.com/api/events/search-events
"""

from typing import Any, Dict, List, Optional
import structlog

from app.services.ingestion.base_client import BaseAPIClient
from app.core.config import settings

logger = structlog.get_logger()


class PredictHQClient(BaseAPIClient):
    BASE_URL = "https://api.predicthq.com/v1"
    RATE_LIMIT = 5
    TIMEOUT = 15.0

    def _headers(self) -> Dict[str, str]:
        if not settings.is_api_configured("predicthq"):
            raise RuntimeError(
                "PredictHQ API not configured. Add PREDICT_HQ_TOKEN to .env"
            )
        return {"Authorization": f"Bearer {settings.PREDICT_HQ_TOKEN}"}

    async def search_events(
        self,
        country: str = "IN",
        category: Optional[str] = None,
        active_gte: Optional[str] = None,   # ISO date, e.g. "2026-08-01"
        active_lte: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Search real events with PredictHQ's demand-significance scoring.
        category: comma-separated, e.g. "concerts,festivals,performing-arts,sports"
        """
        params: Dict[str, Any] = {
            "country": country,
            "limit": min(limit, 200),
            "offset": offset,
            "sort": "rank",
        }
        if category:
            params["category"] = category
        if active_gte:
            params["active.gte"] = active_gte
        if active_lte:
            params["active.lte"] = active_lte

        data = await self.get("/events/", params=params, headers=self._headers())
        results = data.get("results", [])
        return {
            "events": [self._normalize_event(e) for e in results],
            "count": data.get("count", 0),
            "next": data.get("next"),
        }

    @staticmethod
    def _normalize_event(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten to LiveIQ format. rank/local_rank/phq_attendance are the
        real demand signals this client exists to provide — surfaced
        as-is, never estimated or backfilled if PredictHQ omits them
        (phq_attendance in particular is only populated for categories
        PredictHQ models attendance for; None means "not provided by
        PredictHQ," not "zero attendance").
        """
        location = raw.get("location") or []
        entities = raw.get("entities", [])
        venue_entity = next((e for e in entities if e.get("type") == "venue"), None)

        return {
            "predicthq_id": raw.get("id"),
            "title": raw.get("title"),
            "category": raw.get("category"),
            "labels": raw.get("labels", []),
            "start": raw.get("start"),
            "end": raw.get("end"),
            "timezone": raw.get("timezone"),
            "rank": raw.get("rank"),
            "local_rank": raw.get("local_rank"),
            "phq_attendance": raw.get("phq_attendance"),
            "latitude": location[1] if len(location) == 2 else None,
            "longitude": location[0] if len(location) == 2 else None,
            "venue_name": venue_entity.get("name") if venue_entity else None,
            "country": raw.get("country"),
        }

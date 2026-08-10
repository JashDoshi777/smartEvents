"""
LiveIQ — TMDB (The Movie Database) Client
Data collected:
  - Trending movies/series in India
  - Movie/show details: box office, ratings, cast
  - Person search: actors, directors
  - Upcoming releases
  - OTT availability (via watch providers)
"""

from typing import Any, Dict, List, Optional
import structlog

from app.services.ingestion.base_client import BaseAPIClient
from app.core.config import settings

logger = structlog.get_logger()

INDIA_REGION_CODE = "IN"
INDIA_LANGUAGE = "hi-IN"


class TMDBClient(BaseAPIClient):
    BASE_URL = "https://api.themoviedb.org/3"
    RATE_LIMIT = 10         # TMDB allows 40 req/10s; we stay conservative
    TIMEOUT = 10.0

    # Image base URL (TMDB doesn't include this in responses)
    IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

    def _headers(self) -> Dict[str, str]:
        if not settings.is_api_configured("tmdb"):
            raise RuntimeError(
                "TMDB API not configured. Add TMDB_ACCESS_TOKEN to .env "
                "(use the Read Access Token, not the API key)"
            )
        return {
            "Authorization": f"Bearer {settings.TMDB_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

    # ─── Trending ──────────────────────────────────────────────────────────────

    async def get_trending_movies(
        self, time_window: str = "week", region: str = INDIA_REGION_CODE
    ) -> List[Dict[str, Any]]:
        """
        Trending movies in India this week.
        time_window: 'day' or 'week'
        """
        data = await self.get(
            f"/trending/movie/{time_window}",
            params={"region": region},
            headers=self._headers(),
        )
        return [self._normalize_movie(m) for m in data.get("results", [])]

    async def get_trending_tv(self, time_window: str = "week") -> List[Dict[str, Any]]:
        """Trending TV/OTT series globally (filter by Indian content in processing)."""
        data = await self.get(
            f"/trending/tv/{time_window}",
            headers=self._headers(),
        )
        return [self._normalize_tv(s) for s in data.get("results", [])]

    async def get_trending_people(self, time_window: str = "week") -> List[Dict[str, Any]]:
        """Trending celebrities — actors, directors."""
        data = await self.get(
            f"/trending/person/{time_window}",
            headers=self._headers(),
        )
        return [self._normalize_person(p) for p in data.get("results", [])]

    # ─── Movie Details ─────────────────────────────────────────────────────────

    async def get_movie(self, movie_id: int) -> Dict[str, Any]:
        """Full movie details including box office, runtime, cast."""
        data = await self.get(
            f"/movie/{movie_id}",
            params={"append_to_response": "credits,videos,watch/providers"},
            headers=self._headers(),
        )
        return self._normalize_movie_detail(data)

    async def get_upcoming_movies(
        self, region: str = INDIA_REGION_CODE, page: int = 1
    ) -> Dict[str, Any]:
        """Movies releasing soon in India — useful for competition calendar."""
        data = await self.get(
            "/movie/upcoming",
            params={"region": region, "page": page},
            headers=self._headers(),
        )
        return {
            "movies": [self._normalize_movie(m) for m in data.get("results", [])],
            "total_pages": data.get("total_pages", 0),
            "total_results": data.get("total_results", 0),
        }

    async def search_movie(self, query: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search movies by title."""
        params: Dict[str, Any] = {
            "query": query,
            "region": INDIA_REGION_CODE,
        }
        if year:
            params["year"] = year
        data = await self.get("/search/movie", params=params, headers=self._headers())
        return [self._normalize_movie(m) for m in data.get("results", [])]

    async def search_person(self, name: str) -> List[Dict[str, Any]]:
        """Search for actors, directors, comedians."""
        data = await self.get(
            "/search/person",
            params={"query": name},
            headers=self._headers(),
        )
        return [self._normalize_person(p) for p in data.get("results", [])]

    async def get_person(self, person_id: int) -> Dict[str, Any]:
        """Full person profile including filmography."""
        data = await self.get(
            f"/person/{person_id}",
            params={"append_to_response": "movie_credits,tv_credits,external_ids"},
            headers=self._headers(),
        )
        return self._normalize_person_detail(data)

    async def get_movie_watch_providers(self, movie_id: int) -> Dict[str, Any]:
        """Get OTT streaming availability for a movie in India."""
        data = await self.get(
            f"/movie/{movie_id}/watch/providers",
            headers=self._headers(),
        )
        results = data.get("results", {})
        india_data = results.get("IN", {})
        return {
            "streaming": [p.get("provider_name") for p in india_data.get("flatrate", [])],
            "rent": [p.get("provider_name") for p in india_data.get("rent", [])],
            "buy": [p.get("provider_name") for p in india_data.get("buy", [])],
            "link": india_data.get("link"),
        }

    # ─── Normalization ─────────────────────────────────────────────────────────

    def _normalize_movie(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tmdb_id": raw.get("id"),
            "title": raw.get("title"),
            "original_title": raw.get("original_title"),
            "original_language": raw.get("original_language"),
            "release_date": raw.get("release_date"),
            "popularity": raw.get("popularity"),        # TMDB's own score
            "vote_average": raw.get("vote_average"),   # 0-10
            "vote_count": raw.get("vote_count"),
            "overview": raw.get("overview", "")[:500],
            "genre_ids": raw.get("genre_ids", []),
            "poster_url": f"{self.IMAGE_BASE}{raw['poster_path']}" if raw.get("poster_path") else None,
            "backdrop_url": f"{self.IMAGE_BASE}{raw['backdrop_path']}" if raw.get("backdrop_path") else None,
        }

    def _normalize_movie_detail(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        base = self._normalize_movie(raw)
        credits = raw.get("credits", {})
        providers = raw.get("watch/providers", {}).get("results", {}).get("IN", {})
        return {
            **base,
            "budget": raw.get("budget"),
            "revenue": raw.get("revenue"),
            "runtime_minutes": raw.get("runtime"),
            "tagline": raw.get("tagline"),
            "status": raw.get("status"),
            "genres": [g.get("name") for g in raw.get("genres", [])],
            "cast": [c.get("name") for c in credits.get("cast", [])[:10]],
            "director": next(
                (c.get("name") for c in credits.get("crew", []) if c.get("job") == "Director"),
                None,
            ),
            "streaming_platforms_in": [p.get("provider_name") for p in providers.get("flatrate", [])],
        }

    def _normalize_tv(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tmdb_id": raw.get("id"),
            "title": raw.get("name"),
            "original_language": raw.get("original_language"),
            "first_air_date": raw.get("first_air_date"),
            "popularity": raw.get("popularity"),
            "vote_average": raw.get("vote_average"),
            "vote_count": raw.get("vote_count"),
            "poster_url": f"{self.IMAGE_BASE}{raw['poster_path']}" if raw.get("poster_path") else None,
        }

    def _normalize_person(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tmdb_person_id": raw.get("id"),
            "name": raw.get("name"),
            "popularity": raw.get("popularity"),
            "known_for_department": raw.get("known_for_department"),
            "profile_url": f"{self.IMAGE_BASE}{raw['profile_path']}" if raw.get("profile_path") else None,
            "known_for": [
                kf.get("title") or kf.get("name")
                for kf in raw.get("known_for", [])
            ],
        }

    def _normalize_person_detail(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        base = self._normalize_person(raw)
        external = raw.get("external_ids", {})
        return {
            **base,
            "biography": raw.get("biography", "")[:1000],
            "birthday": raw.get("birthday"),
            "place_of_birth": raw.get("place_of_birth"),
            "instagram_id": external.get("instagram_id"),
            "twitter_id": external.get("twitter_id"),
            "imdb_id": external.get("imdb_id"),
        }

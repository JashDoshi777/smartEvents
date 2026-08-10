"""
LiveIQ — Last.fm API Client
Replaces Spotify (which now requires Premium) for music data.

Last.fm is 100% free and provides:
  - Artist listener count (monthly), total play count
  - Artist tags / genres
  - Similar artists (for genre mapping)
  - Artist top tracks
  - Artist top albums
  - Global + India-region trending charts
  - Weekly trending artists chart

API docs: https://www.last.fm/api
Rate limit: 5 req/s (very generous)
No auth needed for read-only endpoints — just an API key.
"""

from typing import Any, Dict, List, Optional
import structlog

from app.services.ingestion.base_client import BaseAPIClient
from app.core.config import settings

logger = structlog.get_logger()

LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"


class LastFMClient(BaseAPIClient):
    BASE_URL = LASTFM_BASE
    RATE_LIMIT = 5          # 5 concurrent — well within Last.fm's 5 req/s limit
    TIMEOUT = 10.0

    def _api_key(self) -> str:
        if not settings.is_api_configured("lastfm"):
            raise RuntimeError(
                "Last.fm API not configured. Add LASTFM_API_KEY to .env\n"
                "Get a free key at: https://www.last.fm/api/account/create"
            )
        return settings.LASTFM_API_KEY

    def _base_params(self) -> Dict[str, str]:
        """Common params for every Last.fm request."""
        return {
            "api_key": self._api_key(),
            "format": "json",
        }

    # ─── Artist Methods ────────────────────────────────────────────────────────

    async def get_artist_info(self, artist_name: str) -> Dict[str, Any]:
        """
        Get full artist profile.
        Returns: listeners (monthly), playcount (all-time), tags/genres,
                 bio, similar artists, MusicBrainz ID.
        """
        data = await self.get(
            "",
            params={
                **self._base_params(),
                "method": "artist.getinfo",
                "artist": artist_name,
                "autocorrect": "1",
            },
        )
        artist = data.get("artist", {})
        return self._normalize_artist(artist)

    async def search_artist(self, name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for artists by name.
        Returns ordered list of matches with listener counts.
        """
        data = await self.get(
            "",
            params={
                **self._base_params(),
                "method": "artist.search",
                "artist": name,
                "limit": limit,
            },
        )
        results = data.get("results", {}).get("artistmatches", {}).get("artist", [])
        if isinstance(results, dict):
            results = [results]  # API returns dict when only 1 result
        return [self._normalize_search_result(a) for a in results]

    async def get_artist_top_tracks(
        self, artist_name: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get artist's most played tracks on Last.fm."""
        data = await self.get(
            "",
            params={
                **self._base_params(),
                "method": "artist.gettoptracks",
                "artist": artist_name,
                "autocorrect": "1",
                "limit": limit,
            },
        )
        tracks = data.get("toptracks", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        return [self._normalize_track(t) for t in tracks]

    async def get_similar_artists(
        self, artist_name: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get similar artists — useful for genre clustering.
        Each result includes a 'match' score 0-1.
        """
        data = await self.get(
            "",
            params={
                **self._base_params(),
                "method": "artist.getsimilar",
                "artist": artist_name,
                "autocorrect": "1",
                "limit": limit,
            },
        )
        artists = data.get("similarartists", {}).get("artist", [])
        if isinstance(artists, dict):
            artists = [artists]
        return [
            {
                "name": a.get("name"),
                "match_score": float(a.get("match", 0)),
                "listeners": int(a.get("listeners", 0)),
                "mbid": a.get("mbid"),
                "image_url": self._extract_image(a.get("image", [])),
            }
            for a in artists
        ]

    async def get_artist_tags(self, artist_name: str) -> List[str]:
        """Get genre tags for an artist (e.g. ['indian hip-hop', 'punjabi', 'rap'])."""
        data = await self.get(
            "",
            params={
                **self._base_params(),
                "method": "artist.gettoptags",
                "artist": artist_name,
                "autocorrect": "1",
            },
        )
        tags = data.get("toptags", {}).get("tag", [])
        if isinstance(tags, dict):
            tags = [tags]
        return [t["name"] for t in tags[:10] if t.get("count", 0) > 5]

    # ─── Charts (Trending) ─────────────────────────────────────────────────────

    async def get_top_artists_global(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Global top artists chart — weekly rolling."""
        data = await self.get(
            "",
            params={
                **self._base_params(),
                "method": "chart.gettopartists",
                "limit": limit,
            },
        )
        artists = data.get("artists", {}).get("artist", [])
        return [self._normalize_chart_artist(a) for a in artists]

    async def get_top_tracks_global(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Global top tracks chart — weekly rolling."""
        data = await self.get(
            "",
            params={
                **self._base_params(),
                "method": "chart.gettoptracks",
                "limit": limit,
            },
        )
        tracks = data.get("tracks", {}).get("track", [])
        return [self._normalize_track(t) for t in tracks]

    async def get_top_artists_by_country(
        self, country: str = "India", limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Top artists in India specifically.
        Uses Last.fm's geo endpoint — actual India listening data.
        """
        data = await self.get(
            "",
            params={
                **self._base_params(),
                "method": "geo.gettopartists",
                "country": country,
                "limit": limit,
            },
        )
        artists = data.get("topartists", {}).get("artist", [])
        if isinstance(artists, dict):
            artists = [artists]
        return [self._normalize_chart_artist(a) for a in artists]

    async def get_top_tracks_by_country(
        self, country: str = "India", limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Top tracks being played in India right now."""
        data = await self.get(
            "",
            params={
                **self._base_params(),
                "method": "geo.gettoptracks",
                "country": country,
                "limit": limit,
            },
        )
        tracks = data.get("tracks", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        return [self._normalize_track(t) for t in tracks]

    # ─── Normalization ─────────────────────────────────────────────────────────

    @staticmethod
    def _extract_image(images: List[Dict]) -> Optional[str]:
        """Last.fm returns multiple image sizes — get the largest."""
        if not images:
            return None
        # Sizes: small, medium, large, extralarge, mega
        for size in ["extralarge", "mega", "large", "medium"]:
            for img in images:
                if img.get("size") == size and img.get("#text"):
                    return img["#text"]
        # Fallback to last non-empty
        for img in reversed(images):
            if img.get("#text"):
                return img["#text"]
        return None

    def _normalize_artist(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        stats = raw.get("stats", {})
        tags = raw.get("tags", {}).get("tag", [])
        if isinstance(tags, dict):
            tags = [tags]
        similar = raw.get("similar", {}).get("artist", [])
        if isinstance(similar, dict):
            similar = [similar]

        return {
            "lastfm_mbid": raw.get("mbid"),
            "name": raw.get("name"),
            "listeners": int(stats.get("listeners", 0)),
            "playcount": int(stats.get("playcount", 0)),
            "tags": [t.get("name") for t in tags[:5]],
            "similar_artists": [s.get("name") for s in similar[:5]],
            "bio_summary": raw.get("bio", {}).get("summary", "")[:500],
            "lastfm_url": raw.get("url"),
            "image_url": self._extract_image(raw.get("image", [])),
        }

    def _normalize_search_result(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": raw.get("name"),
            "listeners": int(raw.get("listeners", 0)),
            "mbid": raw.get("mbid"),
            "lastfm_url": raw.get("url"),
            "image_url": self._extract_image(raw.get("image", [])),
        }

    def _normalize_track(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        artist = raw.get("artist", {})
        return {
            "name": raw.get("name"),
            "artist_name": artist.get("name") if isinstance(artist, dict) else artist,
            "playcount": int(raw.get("playcount", 0)),
            "listeners": int(raw.get("listeners", 0)),
            "lastfm_url": raw.get("url"),
            "image_url": self._extract_image(raw.get("image", [])),
        }

    def _normalize_chart_artist(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "rank": int(raw.get("@attr", {}).get("rank", 0)),
            "name": raw.get("name"),
            "listeners": int(raw.get("listeners", 0)),
            "playcount": int(raw.get("playcount", 0)),
            "mbid": raw.get("mbid"),
            "lastfm_url": raw.get("url"),
            "image_url": self._extract_image(raw.get("image", [])),
        }

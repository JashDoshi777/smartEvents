"""
LiveIQ — Spotify Client
Data collected:
  - Artist search by name → ID, followers, popularity, genres, images
  - Artist top tracks → track names, popularity, preview URLs
  - Related artists → for genre mapping
  - Global/India charts → trending tracks (Sprint 2)
"""

from typing import Any, Dict, List, Optional
import base64
import time
import structlog
import httpx

from app.services.ingestion.base_client import BaseAPIClient
from app.core.config import settings

logger = structlog.get_logger()


class SpotifyClient(BaseAPIClient):
    BASE_URL = "https://api.spotify.com/v1"
    RATE_LIMIT = 5          # Spotify allows ~180 req/min; keep conservative
    TIMEOUT = 10.0

    # Separate token endpoint
    _TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(self):
        super().__init__()
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    async def _ensure_token(self):
        """
        Client Credentials OAuth flow.
        Tokens expire in 3600s — refresh 60s before expiry.
        """
        if self._access_token and time.monotonic() < self._token_expires_at - 60:
            return

        if not settings.is_api_configured("spotify"):
            raise RuntimeError(
                "Spotify API not configured. Add SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET to .env"
            )

        credentials = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()

        async with httpx.AsyncClient(timeout=10.0) as token_client:
            resp = await token_client.post(
                self._TOKEN_URL,
                headers={
                    "Authorization": f"Basic {encoded}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
            )
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        self._token_expires_at = time.monotonic() + data["expires_in"]
        logger.info("Spotify token refreshed", expires_in_seconds=data["expires_in"])

    async def _auth_headers(self) -> Dict[str, str]:
        await self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    # ─── Public Methods ────────────────────────────────────────────────────────

    async def search_artist(self, name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for artists by name.
        Returns list of artist objects with: id, name, popularity, followers,
        genres, images, external_urls.
        """
        headers = await self._auth_headers()
        data = await self.get(
            "/search",
            params={"q": name, "type": "artist", "limit": limit, "market": "IN"},
            headers=headers,
        )
        artists = data.get("artists", {}).get("items", [])
        return [self._normalize_artist(a) for a in artists]

    async def get_artist(self, artist_id: str) -> Dict[str, Any]:
        """Fetch full artist profile by Spotify ID."""
        headers = await self._auth_headers()
        data = await self.get(f"/artists/{artist_id}", headers=headers)
        return self._normalize_artist(data)

    async def get_artist_top_tracks(
        self, artist_id: str, market: str = "IN"
    ) -> List[Dict[str, Any]]:
        """Get artist's top 10 tracks in a market."""
        headers = await self._auth_headers()
        data = await self.get(
            f"/artists/{artist_id}/top-tracks",
            params={"market": market},
            headers=headers,
        )
        return [self._normalize_track(t) for t in data.get("tracks", [])]

    async def get_related_artists(self, artist_id: str) -> List[Dict[str, Any]]:
        """Get up to 20 related artists — useful for genre similarity mapping."""
        headers = await self._auth_headers()
        data = await self.get(f"/artists/{artist_id}/related-artists", headers=headers)
        return [self._normalize_artist(a) for a in data.get("artists", [])]

    async def get_several_artists(self, artist_ids: List[str]) -> List[Dict[str, Any]]:
        """Batch fetch up to 50 artists in a single request."""
        headers = await self._auth_headers()
        data = await self.get(
            "/artists",
            params={"ids": ",".join(artist_ids[:50])},
            headers=headers,
        )
        return [self._normalize_artist(a) for a in data.get("artists", []) if a]

    # ─── Normalization ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_artist(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten Spotify artist object to our internal format."""
        images = raw.get("images", [])
        return {
            "spotify_id": raw.get("id"),
            "name": raw.get("name"),
            "popularity": raw.get("popularity"),        # 0-100
            "followers": raw.get("followers", {}).get("total"),
            "genres": raw.get("genres", []),
            "image_url": images[0]["url"] if images else None,
            "spotify_url": raw.get("external_urls", {}).get("spotify"),
        }

    @staticmethod
    def _normalize_track(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten Spotify track to our internal format."""
        album = raw.get("album", {})
        images = album.get("images", [])
        return {
            "spotify_id": raw.get("id"),
            "name": raw.get("name"),
            "popularity": raw.get("popularity"),
            "duration_ms": raw.get("duration_ms"),
            "preview_url": raw.get("preview_url"),
            "album_name": album.get("name"),
            "release_date": album.get("release_date"),
            "cover_url": images[0]["url"] if images else None,
        }

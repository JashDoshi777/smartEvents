"""
LiveIQ — YouTube Data API v3 Client
Data collected:
  - Channel stats: subscribers, total views, video count
  - Video search: find videos by artist/keyword
  - Video details: views, likes, comments, publish date
  - Trending music videos (India)
"""

from typing import Any, Dict, List, Optional
import structlog

from app.services.ingestion.base_client import BaseAPIClient
from app.core.config import settings

logger = structlog.get_logger()

# YouTube region codes for major Indian cities
INDIA_REGION_CODE = "IN"


class YouTubeClient(BaseAPIClient):
    BASE_URL = "https://www.googleapis.com/youtube/v3"
    RATE_LIMIT = 5      # YouTube quota: 10,000 units/day — be conservative
    TIMEOUT = 10.0

    def _api_key(self) -> str:
        if not settings.is_api_configured("youtube"):
            raise RuntimeError(
                "YouTube API not configured. Add YOUTUBE_API_KEY to .env"
            )
        return settings.YOUTUBE_API_KEY

    # ─── Public Methods ────────────────────────────────────────────────────────

    async def search_channel(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search for artist/brand YouTube channels."""
        data = await self.get(
            "/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "channel",
                "maxResults": max_results,
                "regionCode": INDIA_REGION_CODE,
                "key": self._api_key(),
            },
        )
        return [self._normalize_channel_item(item) for item in data.get("items", [])]

    async def get_channel_stats(self, channel_id: str) -> Dict[str, Any]:
        """
        Get channel statistics.
        Returns: subscribers, total views, video count, channel title.
        Cost: 1 quota unit.
        """
        data = await self.get(
            "/channels",
            params={
                "part": "snippet,statistics,brandingSettings",
                "id": channel_id,
                "key": self._api_key(),
            },
        )
        items = data.get("items", [])
        if not items:
            return {}
        return self._normalize_channel(items[0])

    async def get_video_details(self, video_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get full details for up to 50 videos in one request.
        Returns: views, likes, comments, duration, tags, publish date.
        Cost: 1 quota unit per call.
        """
        data = await self.get(
            "/videos",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(video_ids[:50]),
                "key": self._api_key(),
            },
        )
        return [self._normalize_video(item) for item in data.get("items", [])]

    async def search_videos(
        self,
        query: str,
        max_results: int = 10,
        order: str = "relevance",  # or 'viewCount', 'date'
        published_after: Optional[str] = None,  # RFC3339 e.g. '2024-01-01T00:00:00Z'
    ) -> List[Dict[str, Any]]:
        """
        Search videos by keyword.
        Cost: 100 quota units — use sparingly.
        """
        params: Dict[str, Any] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "order": order,
            "regionCode": INDIA_REGION_CODE,
            "relevanceLanguage": "hi,en",
            "key": self._api_key(),
        }
        if published_after:
            params["publishedAfter"] = published_after

        data = await self.get("/search", params=params)
        return [self._normalize_search_item(item) for item in data.get("items", [])]

    async def get_trending_music_videos(self, max_results: int = 25) -> List[Dict[str, Any]]:
        """
        Get trending music videos in India.
        videoCategoryId=10 = Music.
        Cost: 1 quota unit.
        """
        data = await self.get(
            "/videos",
            params={
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": INDIA_REGION_CODE,
                "videoCategoryId": "10",
                "maxResults": max_results,
                "key": self._api_key(),
            },
        )
        return [self._normalize_video(item) for item in data.get("items", [])]

    # ─── Normalization ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_channel(raw: Dict[str, Any]) -> Dict[str, Any]:
        stats = raw.get("statistics", {})
        snippet = raw.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})
        return {
            "youtube_channel_id": raw.get("id"),
            "title": snippet.get("title"),
            "description": snippet.get("description", "")[:500],
            "subscribers": int(stats.get("subscriberCount", 0)),
            "total_views": int(stats.get("viewCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
            "thumbnail_url": thumbnails.get("high", {}).get("url"),
            "country": snippet.get("country"),
            "published_at": snippet.get("publishedAt"),
        }

    @staticmethod
    def _normalize_channel_item(raw: Dict[str, Any]) -> Dict[str, Any]:
        """From search result (less data than channel endpoint)."""
        snippet = raw.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})
        return {
            "youtube_channel_id": raw.get("id", {}).get("channelId"),
            "title": snippet.get("channelTitle"),
            "description": snippet.get("description", "")[:300],
            "thumbnail_url": thumbnails.get("default", {}).get("url"),
        }

    @staticmethod
    def _normalize_video(raw: Dict[str, Any]) -> Dict[str, Any]:
        snippet = raw.get("snippet", {})
        stats = raw.get("statistics", {})
        return {
            "youtube_video_id": raw.get("id"),
            "title": snippet.get("title"),
            "channel_id": snippet.get("channelId"),
            "channel_title": snippet.get("channelTitle"),
            "published_at": snippet.get("publishedAt"),
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "tags": snippet.get("tags", []),
            "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url"),
        }

    @staticmethod
    def _normalize_search_item(raw: Dict[str, Any]) -> Dict[str, Any]:
        snippet = raw.get("snippet", {})
        return {
            "youtube_video_id": raw.get("id", {}).get("videoId"),
            "title": snippet.get("title"),
            "channel_id": snippet.get("channelId"),
            "channel_title": snippet.get("channelTitle"),
            "published_at": snippet.get("publishedAt"),
            "thumbnail_url": snippet.get("thumbnails", {}).get("default", {}).get("url"),
        }

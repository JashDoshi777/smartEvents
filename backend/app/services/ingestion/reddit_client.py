"""
LiveIQ — Reddit Client (via PRAW async / raw Reddit API)
Data collected:
  - Subreddit posts: for artist/event sentiment
  - Search across Reddit: mentions of entities, events
  - Post sentiment metrics: upvotes, comments, awards, ratio
  - Top posts in India-relevant subreddits: r/bollywood, r/india, r/IPL, etc.
"""

from typing import Any, Dict, List, Optional
import time
import asyncio
import structlog
import httpx

from app.services.ingestion.base_client import BaseAPIClient
from app.core.config import settings

logger = structlog.get_logger()

# Subreddits most relevant to LiveIQ's India events context
INDIA_SUBREDDITS = [
    "bollywood",
    "india",
    "indianmusic",
    "IndianHipHopHeads",
    "cricket",
    "IPL",
    "comedyindia",
    "indiasports",
    "desi",
    "mumbai",
    "bangalore",
    "delhi",
]


class RedditClient(BaseAPIClient):
    BASE_URL = "https://oauth.reddit.com"
    RATE_LIMIT = 3          # Reddit: 60 req/min OAuth; 10 req/min unauthenticated
    TIMEOUT = 10.0

    _AUTH_URL = "https://www.reddit.com/api/v1/access_token"

    def __init__(self):
        super().__init__()
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    async def _ensure_token(self):
        """Reddit OAuth2 client credentials flow."""
        if self._access_token and time.monotonic() < self._token_expires_at - 60:
            return

        if not settings.is_api_configured("reddit"):
            raise RuntimeError(
                "Reddit API not configured. Add REDDIT_CLIENT_ID and "
                "REDDIT_CLIENT_SECRET to .env"
            )

        async with httpx.AsyncClient(timeout=10.0) as auth_client:
            resp = await auth_client.post(
                self._AUTH_URL,
                auth=(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET),
                data={
                    "grant_type": "client_credentials",
                    "device_id": "DO_NOT_TRACK_THIS_DEVICE",
                },
                headers={"User-Agent": settings.REDDIT_USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        self._token_expires_at = time.monotonic() + data["expires_in"]
        logger.info("Reddit token refreshed", expires_in_seconds=data["expires_in"])

    async def _auth_headers(self) -> Dict[str, str]:
        await self._ensure_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": settings.REDDIT_USER_AGENT,
        }

    # ─── Public Methods ────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        subreddit: Optional[str] = None,
        sort: str = "relevance",      # 'relevance', 'hot', 'top', 'new', 'comments'
        time_filter: str = "month",   # 'hour', 'day', 'week', 'month', 'year', 'all'
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Search Reddit posts by keyword.
        Optionally scoped to a specific subreddit.
        """
        headers = await self._auth_headers()
        path = f"/r/{subreddit}/search" if subreddit else "/search"
        params: Dict[str, Any] = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": limit,
            "restrict_sr": bool(subreddit),
            "type": "link",     # 'link' = posts
        }
        data = await self.get(path, params=params, headers=headers)
        posts = data.get("data", {}).get("children", [])
        return [self._normalize_post(p["data"]) for p in posts if p.get("kind") == "t3"]

    async def get_subreddit_hot(
        self, subreddit: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        """Get hot posts from a specific subreddit."""
        headers = await self._auth_headers()
        data = await self.get(
            f"/r/{subreddit}/hot",
            params={"limit": limit},
            headers=headers,
        )
        posts = data.get("data", {}).get("children", [])
        return [self._normalize_post(p["data"]) for p in posts if p.get("kind") == "t3"]

    async def get_subreddit_top(
        self,
        subreddit: str,
        time_filter: str = "week",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Get top posts from a subreddit in a time window."""
        headers = await self._auth_headers()
        data = await self.get(
            f"/r/{subreddit}/top",
            params={"t": time_filter, "limit": limit},
            headers=headers,
        )
        posts = data.get("data", {}).get("children", [])
        return [self._normalize_post(p["data"]) for p in posts if p.get("kind") == "t3"]

    async def get_india_artist_mentions(
        self,
        artist_name: str,
        days: int = 7,
    ) -> Dict[str, Any]:
        """
        Aggregated view of an artist's Reddit presence across India subreddits.
        Returns mention count, avg score, top posts.
        """
        time_filter = "week" if days <= 7 else "month"
        all_posts = []

        # Search across India-relevant subreddits in parallel
        tasks = [
            self.search(artist_name, subreddit=sub, time_filter=time_filter, limit=10)
            for sub in INDIA_SUBREDDITS[:5]  # Limit to avoid rate limiting
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_posts.extend(result)

        # Also do a global search
        global_posts = await self.search(artist_name, time_filter=time_filter, limit=15)
        all_posts.extend(global_posts)

        if not all_posts:
            return {"mentions": 0, "avg_score": 0, "avg_sentiment_score": 0, "top_posts": []}

        scores = [p["score"] for p in all_posts]
        return {
            "mentions": len(all_posts),
            "avg_score": sum(scores) / len(scores),
            "max_score": max(scores),
            "total_comments": sum(p["num_comments"] for p in all_posts),
            "top_posts": sorted(all_posts, key=lambda x: x["score"], reverse=True)[:5],
            "subreddits_found": list({p["subreddit"] for p in all_posts}),
        }

    # ─── Normalization ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_post(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "reddit_id": raw.get("id"),
            "title": raw.get("title"),
            "subreddit": raw.get("subreddit"),
            "author": raw.get("author"),
            "score": raw.get("score", 0),           # upvotes - downvotes
            "upvote_ratio": raw.get("upvote_ratio", 0.5),
            "num_comments": raw.get("num_comments", 0),
            "total_awards": raw.get("total_awards_received", 0),
            "url": f"https://reddit.com{raw.get('permalink', '')}",
            "selftext": raw.get("selftext", "")[:500] if raw.get("selftext") else "",
            "created_utc": raw.get("created_utc"),
            "is_video": raw.get("is_video", False),
            "flair": raw.get("link_flair_text"),
        }

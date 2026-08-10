"""
LiveIQ — NewsAPI Client
Data collected:
  - News articles mentioning entities (artists, movies, sports stars)
  - Source sentiment: positive/negative coverage ratio
  - Breaking news alerts: controversy, award wins, viral moments
  - Top headlines in India by category: entertainment, sports, business
"""

from typing import Any, Dict, List
from datetime import datetime, timedelta
import structlog

from app.services.ingestion.base_client import BaseAPIClient
from app.core.config import settings

logger = structlog.get_logger()


class NewsAPIClient(BaseAPIClient):
    BASE_URL = "https://newsapi.org/v2"
    RATE_LIMIT = 5          # NewsAPI free: 100 req/day; paid: no limit
    TIMEOUT = 10.0

    def _api_key(self) -> str:
        if not settings.is_api_configured("newsapi"):
            raise RuntimeError(
                "NewsAPI not configured. Add NEWSAPI_KEY to .env"
            )
        return settings.NEWSAPI_KEY

    # ─── Public Methods ────────────────────────────────────────────────────────

    async def search_entity_news(
        self,
        entity_name: str,
        days_back: int = 7,
        language: str = "en",
        sort_by: str = "relevancy",     # 'relevancy', 'popularity', 'publishedAt'
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Search all news articles mentioning an entity.
        Returns articles with source, title, description, publish date.
        """
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        data = await self.get(
            "/everything",
            params={
                "q": entity_name,
                "from": from_date,
                "language": language,
                "sortBy": sort_by,
                "pageSize": page_size,
                "apiKey": self._api_key(),
            },
        )

        articles = [self._normalize_article(a) for a in data.get("articles", [])]
        return {
            "entity": entity_name,
            "total_results": data.get("totalResults", 0),
            "articles": articles,
            "from_date": from_date,
        }

    async def get_india_entertainment_headlines(self, page_size: int = 20) -> List[Dict[str, Any]]:
        """Top entertainment headlines from India sources."""
        data = await self.get(
            "/top-headlines",
            params={
                "country": "in",
                "category": "entertainment",
                "pageSize": page_size,
                "apiKey": self._api_key(),
            },
        )
        return [self._normalize_article(a) for a in data.get("articles", [])]

    async def get_india_sports_headlines(self, page_size: int = 20) -> List[Dict[str, Any]]:
        """Top sports headlines from India sources."""
        data = await self.get(
            "/top-headlines",
            params={
                "country": "in",
                "category": "sports",
                "pageSize": page_size,
                "apiKey": self._api_key(),
            },
        )
        return [self._normalize_article(a) for a in data.get("articles", [])]

    async def search_controversy(self, entity_name: str, days_back: int = 30) -> Dict[str, Any]:
        """
        Detect controversy and PR risk.
        Searches for entity name + negative keywords.
        """
        controversy_keywords = [
            "controversy", "scandal", "banned", "arrested", "lawsuit",
            "cancellation", "backlash", "controversy",
        ]
        # Deduplicate and take top 5
        unique_keywords = list(dict.fromkeys(controversy_keywords))[:5]
        query = f'"{entity_name}" AND ({" OR ".join(unique_keywords)})'
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        data = await self.get(
            "/everything",
            params={
                "q": query,
                "from": from_date,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 10,
                "apiKey": self._api_key(),
            },
        )
        articles = [self._normalize_article(a) for a in data.get("articles", [])]
        return {
            "entity": entity_name,
            "controversy_article_count": data.get("totalResults", 0),
            "risk_level": "high" if data.get("totalResults", 0) > 5 else (
                "medium" if data.get("totalResults", 0) > 1 else "low"
            ),
            "recent_articles": articles[:5],
        }

    # Alias for backwards-compatibility and ergonomics
    async def search_news(self, query: str, page_size: int = 20, days_back: int = 7) -> Dict[str, Any]:
        """Alias for search_entity_news — use that method directly when possible."""
        return await self.search_entity_news(query, days_back=days_back, page_size=page_size)

    # ─── Normalization ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_article(raw: Dict[str, Any]) -> Dict[str, Any]:
        source = raw.get("source", {})
        return {
            "title": raw.get("title"),
            "description": raw.get("description", "")[:300] if raw.get("description") else "",
            "url": raw.get("url"),
            "source_name": source.get("name"),
            "source_id": source.get("id"),
            "author": raw.get("author"),
            "published_at": raw.get("publishedAt"),
            "image_url": raw.get("urlToImage"),
        }

"""
LiveIQ — Google Trends Client (via pytrends)
Data collected:
  - Interest over time for India (weekly/monthly)
  - Interest by region (state-level India breakdown)
  - Related queries: what people search alongside the entity
  - Trending searches: what's exploding RIGHT NOW in India
  - Comparison of multiple entities (up to 5)

pytrends is an unofficial Google Trends API wrapper.
No API key required — uses Google's web interface internally.
Rate limit: ~1 req/5s to avoid blocks.
"""

import asyncio
import time
from typing import Any, Dict, List
import structlog

logger = structlog.get_logger()


class GoogleTrendsClient:
    """
    Sync pytrends wrapped in async.
    pytrends is a synchronous library — we run it in a thread pool
    to avoid blocking the async event loop.
    """

    RATE_LIMIT_SECONDS = 5      # Wait between requests to avoid 429
    INDIA_GEO = "IN"
    INDIA_TIMEZONE = 330        # IST = UTC+5:30

    def __init__(self):
        self._last_request_at = 0.0

    async def _throttle(self):
        """Ensure we don't hit Google's rate limiter."""
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.RATE_LIMIT_SECONDS:
            await asyncio.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_at = time.monotonic()

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous pytrends call in the thread pool."""
        loop = asyncio.get_running_loop()  # Correct for use inside async context
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    # ─── Public Methods ────────────────────────────────────────────────────────

    async def get_interest_over_time(
        self,
        keywords: List[str],
        timeframe: str = "today 3-m",   # '7d' | '30d' | '3-m' | '12m' | '5-y'
    ) -> Dict[str, Any]:
        """
        Get search interest over time for keywords in India.
        Values are 0-100 (normalized by Google, not absolute).
        """
        if len(keywords) > 5:
            keywords = keywords[:5]     # Google Trends max 5 keywords

        await self._throttle()

        def _fetch():
            from pytrends.request import TrendReq
            pt = TrendReq(hl="en-IN", tz=self.INDIA_TIMEZONE, timeout=(10, 25))
            pt.build_payload(keywords, geo=self.INDIA_GEO, timeframe=timeframe)
            df = pt.interest_over_time()
            if df.empty:
                return {}
            df = df.drop(columns=["isPartial"], errors="ignore")
            return {
                kw: df[kw].tolist()
                for kw in keywords
                if kw in df.columns
            }

        result = await self._run_sync(_fetch)
        return {"keywords": keywords, "timeframe": timeframe, "interest": result}

    async def get_interest_by_region(
        self,
        keywords: List[str],
        resolution: str = "REGION",   # 'COUNTRY' | 'REGION' (state-level) | 'CITY'
    ) -> Dict[str, Any]:
        """
        Get search interest broken down by Indian state.
        Useful for city intelligence — which regions love this artist?
        """
        if len(keywords) > 5:
            keywords = keywords[:5]

        await self._throttle()

        def _fetch():
            from pytrends.request import TrendReq
            pt = TrendReq(hl="en-IN", tz=self.INDIA_TIMEZONE, timeout=(10, 25))
            pt.build_payload(keywords, geo=self.INDIA_GEO, timeframe="today 3-m")
            df = pt.interest_by_region(resolution=resolution, inc_low_vol=True, inc_geo_code=True)
            if df.empty:
                return []
            df = df.reset_index()
            return df.to_dict(orient="records")

        result = await self._run_sync(_fetch)
        return {"keywords": keywords, "resolution": resolution, "regions": result}

    async def get_related_queries(self, keyword: str) -> Dict[str, Any]:
        """
        Get related and rising queries for a keyword in India.
        'Rising' = breakout queries growing fast — great for trend prediction.
        """
        await self._throttle()

        def _fetch():
            from pytrends.request import TrendReq
            pt = TrendReq(hl="en-IN", tz=self.INDIA_TIMEZONE, timeout=(10, 25))
            pt.build_payload([keyword], geo=self.INDIA_GEO, timeframe="today 3-m")
            related = pt.related_queries()
            data = related.get(keyword, {})
            top_df = data.get("top")
            rising_df = data.get("rising")
            return {
                "top": top_df.to_dict(orient="records") if top_df is not None else [],
                "rising": rising_df.to_dict(orient="records") if rising_df is not None else [],
            }

        result = await self._run_sync(_fetch)
        return {"keyword": keyword, **result}

    async def get_trending_searches_india(self) -> List[str]:
        """
        Get TODAY's trending searches in India.
        This is what's exploding RIGHT NOW.
        """
        await self._throttle()

        def _fetch():
            from pytrends.request import TrendReq
            pt = TrendReq(hl="en-IN", tz=self.INDIA_TIMEZONE, timeout=(10, 25))
            df = pt.trending_searches(pn="india")
            return df[0].tolist() if not df.empty else []

        return await self._run_sync(_fetch)

    async def compare_entities(
        self,
        entity_names: List[str],
        timeframe: str = "today 12-m",
    ) -> Dict[str, Any]:
        """
        Compare up to 5 entities head-to-head in India.
        Used by the Artist Intelligence Score comparison feature.
        """
        if len(entity_names) > 5:
            entity_names = entity_names[:5]

        interest = await self.get_interest_over_time(entity_names, timeframe=timeframe)

        # Calculate average interest per entity as a simple score
        scores = {}
        for entity, values in interest.get("interest", {}).items():
            if values:
                scores[entity] = round(sum(values) / len(values), 1)
            else:
                scores[entity] = 0

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return {
            "entities": entity_names,
            "timeframe": timeframe,
            "average_interest_scores": dict(ranked),
            "winner": ranked[0][0] if ranked else None,
            "raw_interest": interest.get("interest", {}),
        }

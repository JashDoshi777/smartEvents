"""
LiveIQ — Redis Client (cache + rate limiting + session store)
"""

import asyncio
import redis.asyncio as aioredis
from app.core.config import settings
import structlog

logger = structlog.get_logger()

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _redis_client


async def close_redis_connection():
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


async def check_redis_connection() -> bool:
    try:
        redis = get_redis()
        await asyncio.wait_for(redis.ping(), timeout=2)
        return True
    except Exception as e:
        logger.warning("Redis unavailable (optional)", error=type(e).__name__)
        return False


async def cache_get(key: str) -> str | None:
    """Get a value from cache. Returns None if not found or expired."""
    try:
        return await get_redis().get(key)
    except Exception:
        return None


async def cache_set(key: str, value: str, ttl_seconds: int = 300) -> bool:
    """Set a cache value with TTL. Returns True on success."""
    try:
        await get_redis().setex(key, ttl_seconds, value)
        return True
    except Exception:
        return False


async def cache_delete(key: str) -> bool:
    """Delete a cache key."""
    try:
        await get_redis().delete(key)
        return True
    except Exception:
        return False


async def cache_invalidate_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern. Returns count of deleted keys."""
    try:
        redis = get_redis()
        keys = await redis.keys(pattern)
        if keys:
            return await redis.delete(*keys)
        return 0
    except Exception:
        return 0

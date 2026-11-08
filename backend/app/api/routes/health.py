"""Health check router."""
import asyncio
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.core.database import check_db_connection, engine
from app.core.response_cache import cache_stats
from app.core.mongodb import check_mongo_connection
from app.core.redis_client import check_redis_connection
from app.core.config import settings

router = APIRouter()


_HEALTH_CACHE: dict = {"at": 0.0, "value": None}


@router.get("/health", summary="System health check")
async def health():
    # Dependency pings are slow when a backing service is down (DNS / TCP
    # timeouts), so probe them concurrently and reuse the result for 30s.
    if _HEALTH_CACHE["value"] and time.monotonic() - _HEALTH_CACHE["at"] < 30:
        return _respond(_HEALTH_CACHE["value"])
    db, mongo, redis = await asyncio.gather(
        check_db_connection(), check_mongo_connection(), check_redis_connection()
    )
    # Postgres is the only hard dependency; Mongo/Redis are optional extras
    # (background workers) and must not flip the whole API to 'degraded'.
    all_healthy = db
    result = {
        "status": "ok" if all_healthy else "degraded",
        "version": settings.APP_VERSION,
        "services": {
            "postgres": "up" if db else "down",
            "mongodb": "up" if mongo else "optional-offline",
            "redis": "up" if redis else "optional-offline",
        },
        "apis_configured": {
            "spotify": settings.is_api_configured("spotify"),
            "youtube": settings.is_api_configured("youtube"),
            "ticketmaster": settings.is_api_configured("ticketmaster"),
            "tmdb": settings.is_api_configured("tmdb"),
            "groq": settings.is_api_configured("groq"),
            "gemini": settings.is_api_configured("gemini"),
            "newsapi": settings.is_api_configured("newsapi"),
            "reddit": settings.is_api_configured("reddit"),
            "lastfm": settings.is_api_configured("lastfm"),
            "mapbox": settings.is_api_configured("mapbox"),
        },
    }
    _HEALTH_CACHE.update(at=time.monotonic(), value=result)
    return _respond(result)


def _live(result: dict) -> dict:
    """Cheap, always-fresh parts (no I/O): response-cache + DB pool stats."""
    pool = engine.pool
    try:
        pool_info = {"size": pool.size(), "checked_out": pool.checkedout(), "overflow": pool.overflow()}
    except Exception:  # pragma: no cover - pool impl without these
        pool_info = {}
    return {**result, "cache": cache_stats(), "db_pool": pool_info}


def _respond(result: dict):
    body = _live(result)
    if result["status"] != "ok":  # load balancers key off the status code
        return JSONResponse(status_code=503, content=body, headers={"Retry-After": "5"})
    return body


@router.get("/", include_in_schema=False)
async def root():
    return {"message": "LiveIQ API — AI-Powered Events Intelligence", "docs": "/docs"}

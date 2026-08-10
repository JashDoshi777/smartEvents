"""Health check router."""
from fastapi import APIRouter
from app.core.database import check_db_connection
from app.core.mongodb import check_mongo_connection
from app.core.redis_client import check_redis_connection
from app.core.config import settings

router = APIRouter()


@router.get("/health", summary="System health check")
async def health():
    db = await check_db_connection()
    mongo = await check_mongo_connection()
    redis = await check_redis_connection()
    all_healthy = db and mongo and redis
    return {
        "status": "ok" if all_healthy else "degraded",
        "version": settings.APP_VERSION,
        "services": {
            "postgres": "up" if db else "down",
            "mongodb": "up" if mongo else "down",
            "redis": "up" if redis else "down",
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


@router.get("/", include_in_schema=False)
async def root():
    return {"message": "LiveIQ API — AI-Powered Events Intelligence", "docs": "/docs"}

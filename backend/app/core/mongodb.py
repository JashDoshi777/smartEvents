"""
LiveIQ — MongoDB Connection (for raw social data, unstructured docs)
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings
import asyncio
import time
import structlog

logger = structlog.get_logger()

_mongo_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(
            settings.MONGO_URL,
            serverSelectionTimeoutMS=1500,
            connectTimeoutMS=1500,
            maxPoolSize=10,
        )
    return _mongo_client


def get_mongo_db() -> AsyncIOMotorDatabase:
    return get_mongo_client()[settings.MONGO_DB_NAME]


async def close_mongo_connection():
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
        logger.info("MongoDB connection closed")


async def check_mongo_connection() -> bool:
    try:
        client = get_mongo_client()
        await asyncio.wait_for(client.admin.command("ping"), timeout=2.5)
        return True
    except Exception as e:
        logger.warning("MongoDB unavailable (optional)", error=type(e).__name__)
        return False


# Negative-cached availability so callers on hot/background paths never pay a
# 1.5s server-selection timeout per call while Mongo is down (it is permanently
# down in dev). Nothing on the request path uses Mongo at all.
_AVAIL = {"ok": False, "checked": 0.0}
_RECHECK_S = 60.0


async def mongo_available() -> bool:
    now = time.monotonic()
    if now - _AVAIL["checked"] < _RECHECK_S:
        return _AVAIL["ok"]
    _AVAIL["ok"] = await check_mongo_connection()
    _AVAIL["checked"] = time.monotonic()
    return _AVAIL["ok"]

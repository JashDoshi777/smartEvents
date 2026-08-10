"""
LiveIQ — MongoDB Connection (for raw social data, unstructured docs)
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings
import structlog

logger = structlog.get_logger()

_mongo_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(
            settings.MONGO_URL,
            serverSelectionTimeoutMS=5000,
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
        await client.admin.command("ping")
        return True
    except Exception as e:
        logger.error("MongoDB connection failed", error=str(e))
        return False

"""
LiveIQ — PostgreSQL Database Connection
Async SQLAlchemy engine with TimescaleDB support.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData, text
from app.core.config import settings
import structlog

logger = structlog.get_logger()

# Naming convention for constraints — important for Alembic migrations
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


# Async engine — used by FastAPI request handlers
# NOTE: statement_cache_size=0 is REQUIRED for Neon's PgBouncer pooler.
# PgBouncer in transaction mode does not support prepared statements.
engine = create_async_engine(
    settings.POSTGRES_URL,
    echo=False,             # SQL echo floods logs and slows every request
    pool_size=8,
    max_overflow=12,
    # pre_ping costs one full network round-trip (~200ms to Neon) on EVERY
    # checkout. A keepalive task (see main.py) keeps the pool warm instead,
    # and a short recycle bounds how stale a pooled connection can get.
    pool_pre_ping=False,
    pool_recycle=240,
    pool_timeout=20,
    connect_args={
        "ssl": "require",                  # SSL required by NeonDB
        "statement_cache_size": 0,         # Required for PgBouncer / Neon pooler
        "server_settings": {"application_name": "liveiq"},
    },
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    """
    FastAPI dependency: yields a DB session per request.
    Automatically commits on success, rolls back on exception.
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables():
    """Create all tables — used only in testing. Production uses Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("All tables created")


async def check_db_connection() -> bool:
    """Health check: verify database is reachable."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return False

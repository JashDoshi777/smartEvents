"""
LiveIQ — PostgreSQL Database Connection
Async SQLAlchemy engine with TimescaleDB support.
"""

import asyncio
from fastapi import Request
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
    # Fail fast when the pool is exhausted: a request waiting >10s for a
    # connection is answered with 503 + Retry-After (see app/core/errors.py)
    # instead of hanging the client for the old 20s.
    pool_timeout=10,
    connect_args={
        "ssl": "require",                  # SSL required by NeonDB
        "statement_cache_size": 0,         # Required for PgBouncer / Neon pooler
        "timeout": 10,                     # TCP/TLS connect timeout (s)
        "command_timeout": 30,             # per-statement client-side timeout (s)
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


# Read-only sessions run in AUTOCOMMIT: no BEGIN / COMMIT-or-ROLLBACK round
# trips. Against a remote DB (~200ms RTT) a default session costs 3 RTTs for a
# single SELECT (BEGIN, SELECT, ROLLBACK on close = ~650ms) versus 1 RTT
# (~200ms) in autocommit - measured, see tests/perf notes. It shares the same
# connection pool as `engine`. Safe because GET/HEAD handlers never write.
_ro_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
ReadOnlySessionLocal = async_sessionmaker(
    _ro_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

AutocommitSessionLocal = ReadOnlySessionLocal  # alias: also used for single-statement writes (atomic by itself)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def get_db(request: Request = None):
    """
    FastAPI dependency: yields a DB session per request.
    GET/HEAD requests get an AUTOCOMMIT session (1 RTT per statement);
    everything else gets a normal transactional session that commits on
    success and rolls back on exception.
    Usage: db: AsyncSession = Depends(get_db)
    """
    factory = ReadOnlySessionLocal if (request is not None and request.method in _SAFE_METHODS) else AsyncSessionLocal
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Global cap on concurrently running fan-out statements so one request (or a
# burst of them) can never drain the 20-connection pool and starve the rest.
_FANOUT = asyncio.Semaphore(12)


async def run_queries(*statements):
    """Run independent read statements CONCURRENTLY, one autocommit session each,
    and return a list of row-lists (``result.all()``) in the same order.

    Latency becomes max(RTT) instead of sum(RTT): 6 queries = ~0.2s, not ~1.3s.
    """
    async def _one(stmt):
        async with _FANOUT:
            async with ReadOnlySessionLocal() as s:
                return (await s.execute(stmt)).all()

    return list(await asyncio.gather(*(_one(st) for st in statements)))


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

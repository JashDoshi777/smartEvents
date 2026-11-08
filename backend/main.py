"""
LiveIQ — Main FastAPI Application
Entry point. Mounts all routers, configures middleware, lifecycle events.
"""

import sys

# See app/workers/celery_app.py for why this is needed: Windows consoles
# default stdout/stderr to cp1252, and real ingested data (e.g. OSM
# addresses containing "Mahārāshtra") crashes SQLAlchemy's SQL-echo
# logger the first time such a character reaches a log call.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import structlog
import logging

# httpx logs full request URLs at INFO — some upstream APIs (NewsAPI, YouTube) take the key as a query param.
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

from app.core.config import settings
from app.core.limiter import limiter
from app.core.errors import register_exception_handlers
from app.core.middleware import RequestContextMiddleware, ErrorBoundaryMiddleware
from app.core.database import check_db_connection, AsyncSessionLocal
from app.core.response_cache import ResponseCacheMiddleware, warm_cache
import asyncio
from sqlalchemy import text, select
from app.core.mongodb import check_mongo_connection, close_mongo_connection
from app.core.redis_client import check_redis_connection, close_redis_connection

# ─── Import all routers ────────────────────────────────────────
from app.api.routes import (
    entities,
    trends,
    cities,
    predict,
    competitors,
    social,
    pricing,
    executive,
    copilot,
    auth,
    recommend,
    psychology,
    health as health_router,
    admin,
)
from app.api.routes import dashboard
from app.api.routes import events
from app.api.routes import notifications
from app.api.routes import pairing
from app.api.routes import forecast
from app.api.routes import watchlist
from app.api.routes import venue_calendar

# Logging: plain (no rich "locals" dump - frame locals can contain secrets/PII),
# request_id bound per request by RequestContextMiddleware.
import logging as _logging

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(colors=False, exception_formatter=structlog.dev.plain_traceback),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(getattr(_logging, str(settings.LOG_LEVEL).upper(), _logging.INFO)),
)
logger = structlog.get_logger()

# Rate limiter lives in app/core/limiter.py (shared with the auth routes).


WARM_PATHS = [
    "/dashboard/summary", "/dashboard/alerts", "/executive/kpis", "/executive/portfolio",
    "/cities/", "/cities/top", "/cities/gaps", "/trends/breakout", "/trends/viral",
    "/trends/regional", "/competitors/intelligence", "/competitors/gaps",
    "/competitors/activity-feed", "/recommend/entities", "/pricing/benchmarks",
    "/social/crisis-alerts", "/copilot/models",
]


async def _db_keepalive():
    """Ping every 60s so pooled Neon connections never go cold (the pool runs
    without pre-ping to avoid a round-trip on every checkout)."""
    while True:
        try:
            await asyncio.sleep(60)
            async with AsyncSessionLocal() as s:
                await s.execute(text("SELECT 1"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("db keepalive failed", error=str(exc))


async def _prewarm(app: FastAPI):
    """Mint a short-lived token for any active user and replay the hot GETs."""
    try:
        from app.models.user import User
        from app.services.auth_service import create_access_token
        async with AsyncSessionLocal() as s:
            user = (await s.execute(select(User).where(User.is_active.is_(True)).limit(1))).scalar_one_or_none()
        if user is None:
            return
        await warm_cache(app, create_access_token(user.id, user.role), WARM_PATHS)
        logger.info("Response cache warmed", paths=len(WARM_PATHS))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("cache prewarm failed", error=str(exc))


# ─── Lifespan (startup / shutdown) ────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle management."""
    logger.info("LiveIQ API starting up", version=settings.APP_VERSION)

    # Verify all connections on startup
    db_ok, mongo_ok, redis_ok = await asyncio.gather(
        check_db_connection(), check_mongo_connection(), check_redis_connection()
    )

    for problem in settings.secret_key_warnings():
        logger.warning("SECURITY: " + problem + " - set a long random SECRET_KEY before deploying")
    if settings.APP_ENV == "production" and settings.DEBUG:
        logger.warning("SECURITY: DEBUG is enabled in production (exposes /docs)")

    if not db_ok:
        logger.warning("PostgreSQL not reachable at startup")
    if not mongo_ok:
        logger.warning("MongoDB not reachable at startup")
    if not redis_ok:
        logger.warning("Redis not reachable at startup")

    # Log which APIs are configured
    apis = ["spotify", "youtube", "ticketmaster", "tmdb", "gemini", "newsapi", "reddit", "mapbox"]
    for api in apis:
        status = "configured" if settings.is_api_configured(api) else "not configured (key not set)"
        logger.info(f"  {api.capitalize()}: {status}")

    logger.info("Startup complete")

    # Background tasks: keep the DB pool warm and pre-fill the response cache
    # so the first user after a restart gets instant pages.
    bg_tasks = [
        asyncio.create_task(_db_keepalive()),
        asyncio.create_task(_prewarm(app)),
    ]

    yield  # App runs here

    for t in bg_tasks:
        t.cancel()

    # Shutdown: close all connections gracefully
    logger.info("Shutting down LiveIQ API...")
    await close_mongo_connection()
    await close_redis_connection()
    logger.info("Shutdown complete")


# ─── Application Factory ──────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="LiveIQ API",
        description="AI-powered events intelligence platform for Zomato District",
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ─── Middleware (order matters: outermost = last applied) ──
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    # SlowAPIMiddleware is what makes `default_limits` apply to every route
    # automatically — without it, slowapi only enforces limits on routes
    # individually decorated with @limiter.limit(...), and default_limits
    # would silently do nothing.
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(ErrorBoundaryMiddleware)    # unhandled exception -> JSON 500/503 (inside CORS)
    app.add_middleware(ResponseCacheMiddleware)    # outside the boundary: never caches error bodies
    app.add_middleware(RequestContextMiddleware)   # request id, access log, security headers
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,   # explicit origins only (no "*" with credentials)
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID", "Cache-Control"],
        expose_headers=["X-Request-ID", "X-Cache", "Retry-After"],
        max_age=600,
    )
    register_exception_handlers(app)

    # ─── Routers ───────────────────────────────────────────────
    app.include_router(health_router.router, tags=["System"])
    app.include_router(auth.router, prefix="/auth", tags=["Auth"])
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    app.include_router(entities.router, prefix="/entities", tags=["Entity Intelligence"])
    app.include_router(trends.router, prefix="/trends", tags=["Trend Radar"])
    app.include_router(cities.router, prefix="/cities", tags=["City Intelligence"])
    app.include_router(predict.router, prefix="/predict", tags=["Predictions"])
    app.include_router(competitors.router, prefix="/competitors", tags=["Competitor Intel"])
    app.include_router(social.router, prefix="/social", tags=["Social Listening"])
    app.include_router(pricing.router, prefix="/pricing", tags=["Pricing Optimizer"])
    app.include_router(executive.router, prefix="/executive", tags=["Executive Dashboard"])
    app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
    app.include_router(events.router, prefix="/events", tags=["Event Deal Modeler"])
    app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
    app.include_router(pairing.router, prefix="/intelligence", tags=["Artist Pairing"])
    app.include_router(forecast.router, prefix="/intelligence", tags=["Demand Forecasting"])
    app.include_router(watchlist.router, prefix="/watchlist", tags=["Watchlist"])
    app.include_router(venue_calendar.router, prefix="/venues", tags=["Venue Availability"])
    app.include_router(copilot.router, prefix="/copilot", tags=["AI Copilot"])
    app.include_router(recommend.router, prefix="/recommend", tags=["AI Recommendation"])
    app.include_router(psychology.router, prefix="/psychology", tags=["Psychological Demand Analysis"])

    return app


app = create_app()

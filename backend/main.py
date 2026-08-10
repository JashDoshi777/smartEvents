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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import structlog

from app.core.config import settings
from app.core.database import check_db_connection
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
)
from app.api.routes import dashboard
from app.api.routes import events
from app.api.routes import notifications
from app.api.routes import pairing
from app.api.routes import forecast
from app.api.routes import watchlist
from app.api.routes import venue_calendar

logger = structlog.get_logger()

# Per-IP, in-memory (no Redis storage backend configured — acceptable for
# a single-process dev/small deployment; would need a shared storage_uri
# to be correct across multiple backend processes/instances).
# RATE_LIMIT_PER_MINUTE is the default applied to every route; individual
# routes can override with @limiter.limit("N/minute") if they need a
# different ceiling (e.g. auth endpoints tighter, health checks looser).
#
# config_filename="__no_such_file__": Limiter.__init__ unconditionally
# does `open(".env")` (via Starlette's Config) whenever a .env exists in
# the cwd, with no explicit encoding — on Windows that's the locale
# default (cp1252), which can't decode this repo's genuinely-UTF-8 .env
# (it has box-drawing header comments, e.g. "═"), crashing at import
# time. Passing a filename that doesn't exist skips that read entirely
# (Config just warns and moves on) — this app already loads its own
# settings via pydantic-settings, so slowapi's separate config file
# support isn't needed anyway.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    config_filename="__no_such_file__",
)


# ─── Lifespan (startup / shutdown) ────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle management."""
    logger.info("LiveIQ API starting up", version=settings.APP_VERSION)

    # Verify all connections on startup
    db_ok = await check_db_connection()
    mongo_ok = await check_mongo_connection()
    redis_ok = await check_redis_connection()

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

    yield  # App runs here

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
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── Routers ───────────────────────────────────────────────
    app.include_router(health_router.router, tags=["System"])
    app.include_router(auth.router, prefix="/auth", tags=["Auth"])
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

    # ─── Global exception handler ──────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.exception("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc) if settings.DEBUG else None},
        )

    return app


app = create_app()

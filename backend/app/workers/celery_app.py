"""
LiveIQ — Celery Application
Background task workers for data collection and ML jobs.
"""

import sys
import ssl

# On Windows, sys.stdout/stderr default to the console's legacy codepage
# (cp1252), not UTF-8. Real data ingested by these workers legitimately
# contains non-Latin-1 characters (e.g. "Mahārāshtra" from OpenStreetMap
# address data) — SQLAlchemy's SQL-echo logger and structlog both write
# through stdlib `logging`, which writes straight to that misconfigured
# stream, so the first such character crashes the log call with
# UnicodeEncodeError. Reconfiguring the streams to UTF-8 (Python 3.7+)
# fixes this at the source instead of stripping/escaping real data.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

# Upstash's rediss:// URL doesn't carry ssl_cert_reqs as a query param —
# celery's redis transport (unlike redis-py directly) requires it be set
# explicitly via broker/redis_backend_use_ssl, or worker startup crashes
# immediately with "A rediss:// URL must have parameter ssl_cert_reqs".
# CERT_NONE because Upstash's managed cert chain isn't in a local CA
# bundle we control — acceptable here since the transport is already
# TLS-encrypted point-to-point to Upstash, just without cert verification.
_REDIS_TLS_OPTS = {"ssl_cert_reqs": ssl.CERT_NONE}

celery_app = Celery(
    "liveiq",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    broker_use_ssl=_REDIS_TLS_OPTS if settings.CELERY_BROKER_URL.startswith("rediss://") else None,
    redis_backend_use_ssl=_REDIS_TLS_OPTS if settings.CELERY_RESULT_BACKEND.startswith("rediss://") else None,
    include=[
        "app.workers.entity_metrics",
        "app.workers.trend_signals",
        "app.workers.social_listening",
        "app.workers.competitor_intel",
        "app.workers.event_sync",
        "app.workers.anomaly_detection",  # Sprint 4 ML: IsolationForest breakout detection
        "app.workers.notification_signals",  # Sprint 5D: persisted notification signals
        "app.workers.artist_discovery",  # Auto-discovery of new/trending artists
        "app.workers.predicthq_sync",  # Master data: PredictHQ real demand-signal events
        "app.workers.restaurant_sync",  # Master data: Foursquare + OSM real restaurant listings
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,           # Worker acks AFTER task completes (safer)
    worker_prefetch_multiplier=1,  # One task at a time per worker process
    task_max_retries=3,
    task_default_retry_delay=60,   # 60s between retries
    result_expires=86400,          # Results expire after 24h

    # ─── Beat schedule ────────────────────────────────────────
    beat_schedule={
        # Entity metrics: every 6 hours
        "sync-entity-metrics": {
            "task": "app.workers.entity_metrics.sync_all_active_entities",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        # Trend signals: every 1 hour
        "sync-trend-signals": {
            "task": "app.workers.trend_signals.detect_breakout_signals",
            "schedule": crontab(minute=30),  # 30 min past every hour
        },
        # Social listening: every 30 minutes
        "sync-social-listening": {
            "task": "app.workers.social_listening.collect_social_mentions",
            "schedule": crontab(minute="*/30"),
        },
        # Competitor scrape: every 12 hours
        "scrape-competitors": {
            "task": "app.workers.competitor_intel.scrape_all_platforms",
            "schedule": crontab(minute=0, hour="*/12"),
        },
        # Event sync: every 4 hours
        "sync-events": {
            "task": "app.workers.event_sync.sync_upcoming_events",
            "schedule": crontab(minute=15, hour="*/4"),
        },
        # Anomaly detection (ML): every 6 hours, 15 min after entity_metrics
        "detect-breakouts": {
            "task": "app.workers.anomaly_detection.detect_breakouts",
            "schedule": crontab(minute=15, hour="*/6"),
        },
        # Notification signals: every 15 minutes
        "generate-notification-signals": {
            "task": "app.workers.notification_signals.generate_notification_signals",
            "schedule": crontab(minute="*/15"),
        },
        # Artist discovery: every 6 hours, same cadence as entity_metrics so
        # a newly discovered artist gets scored within one cycle
        "discover-new-artists": {
            "task": "app.workers.artist_discovery.discover_new_artists",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        # PredictHQ sync: every 6 hours, offset from other 6h jobs
        "sync-predicthq-events": {
            "task": "app.workers.predicthq_sync.sync_predicthq_events",
            "schedule": crontab(minute=45, hour="*/6"),
        },
        # Restaurant sync: daily — listings change far less often than events
        "sync-restaurants": {
            "task": "app.workers.restaurant_sync.sync_restaurants",
            "schedule": crontab(minute=30, hour=3),  # 3:30 AM IST, off-peak
        },
    },
)

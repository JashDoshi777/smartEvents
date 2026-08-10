"""
LiveIQ — PredictHQ Sync Worker (Master Data)
Pulls real Indian events with PredictHQ's demand-significance scoring
(rank, local_rank, phq_attendance) and upserts into the shared `events`
table via the same real venue/entity-resolution logic already used for
District/BookMyShow scraped events — a second, independently-sourced,
real signal that both grows event coverage and cross-validates it.

Schedule: every 6 hours (see celery_app.py beat_schedule).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import structlog
from celery import Task

from app.workers.celery_app import celery_app
from app.workers.run_utils import run_async
from app.services.ingestion.predicthq_client import PredictHQClient
from app.services.ingestion.scraped_event_upsert import upsert_scraped_events

logger = structlog.get_logger()

CATEGORIES = "concerts,festivals,performing-arts,sports,community"
LOOKAHEAD_DAYS = 180  # events starting within the next 6 months
SOURCE = "predicthq"


def _normalize(raw: Dict[str, Any]) -> Dict[str, Any] | None:
    """Map a PredictHQClient event dict -> the shape upsert_scraped_events expects."""
    if not raw.get("predicthq_id") or not raw.get("title") or not raw.get("start"):
        return None
    try:
        event_dt = datetime.fromisoformat(raw["start"].replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None

    category_map = {
        "concerts": "music",
        "festivals": "festival",
        "performing-arts": "theatre",
        "sports": "sports",
        "community": "experience",
    }
    # PredictHQ's real taxonomy includes categories beyond the 5 this
    # project queries for (expos, conferences, academic, observances,
    # etc. — CATEGORIES only requests the 5 mapped ones, but PredictHQ
    # can still return adjacent/related categories in some responses).
    # Defaulting an unmapped category to "music" would silently
    # mislabel a real event's category — "experience" is this
    # codebase's real neutral/catch-all category value (already used
    # by pricing_engine.py's _CATEGORY_LIST), not a fabricated one.
    category = category_map.get(raw.get("category"), "experience")

    return {
        "external_id": raw["predicthq_id"],
        "source": SOURCE,
        "title": raw["title"],
        "category": category,
        "event_date": event_dt,
        "venue_name": raw.get("venue_name"),
        "city": None,  # PredictHQ gives lat/lng, not a city name — venue-name-only match
        "ticket_price_min": None,
        "ticket_price_max": None,
        "booking_url": None,
        "cover_image_url": None,
        "status": "upcoming",
        "scraped_at": datetime.now(timezone.utc),
        "predicthq_rank": raw.get("rank"),
        "predicthq_local_rank": raw.get("local_rank"),
        "predicthq_predicted_attendance": raw.get("phq_attendance"),
    }


async def _run_sync() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    active_lte = (now + timedelta(days=LOOKAHEAD_DAYS)).date().isoformat()

    all_raw: List[Dict[str, Any]] = []
    offset = 0
    # Unlike restaurant_sync.py's per-city try/except (a missing API key
    # or network failure there just means one city returns []), a
    # missing PREDICT_HQ_TOKEN or transient failure here used to
    # propagate straight out of _run_sync into the Celery task's
    # exception handler, triggering 3 full retries at 300s intervals
    # instead of degrading gracefully with an empty result — this is
    # the one-time sync/manual-run path too, where a crash is worse
    # than a documented empty return.
    try:
        async with PredictHQClient() as client:
            while True:
                result = await client.search_events(
                    country="IN",
                    category=CATEGORIES,
                    active_gte=now.date().isoformat(),
                    active_lte=active_lte,
                    limit=200,
                    offset=offset,
                )
                events = result.get("events", [])
                all_raw.extend(events)
                if not result.get("next") or len(events) < 200:
                    break
                offset += 200
                if offset >= 1000:  # hard cap — stay bounded even on a huge result set
                    logger.warning("predicthq_sync: hit 1000-event fetch cap, stopping pagination")
                    break
    except Exception as exc:
        logger.warning("predicthq_sync: PredictHQ fetch failed, returning empty result", error=str(exc))
        return {"status": "fetch_failed", "total_fetched": 0, "error": str(exc)}

    normalized = [n for raw in all_raw if (n := _normalize(raw)) is not None]
    skipped_normalize = len(all_raw) - len(normalized)

    if not normalized:
        return {"status": "no_events", "total_fetched": len(all_raw)}

    db_result = await upsert_scraped_events(normalized)
    logger.info("predicthq_sync: cycle complete", fetched=len(all_raw), skipped_normalize=skipped_normalize, **db_result)

    return {
        "status": "ok",
        "total_fetched": len(all_raw),
        "skipped_normalize": skipped_normalize,
        "synced_at": now.isoformat(),
        **db_result,
    }


@celery_app.task(
    name="app.workers.predicthq_sync.sync_predicthq_events",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def sync_predicthq_events(self: Task):
    logger.info("predicthq_sync: starting sync cycle")
    try:
        result = run_async(_run_sync())
        logger.info("predicthq_sync: cycle complete", **result)
        return result
    except Exception as exc:
        logger.error("predicthq_sync: cycle failed", error=str(exc))
        raise self.retry(exc=exc)

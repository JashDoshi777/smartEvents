"""
LiveIQ — Entity Metrics Collection Worker (Sprint 2C)
Fetches Last.fm, YouTube, Google Trends, and NewsAPI data
for all active entities and writes to PostgreSQL (processed scores).

Schedule: every 6 hours (see celery_app.py beat_schedule)
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from celery import Task
from sqlalchemy import select, update

from app.workers.celery_app import celery_app
from app.workers.run_utils import run_async
from app.services.ingestion.lastfm_client import LastFMClient
from app.services.ingestion.youtube_client import YouTubeClient
from app.services.ingestion.google_trends_client import GoogleTrendsClient
from app.services.ingestion.newsapi_client import NewsAPIClient
from app.core.database import AsyncSessionLocal
from app.models.entity import Entity
from app.models.metrics import EntityMetric

logger = structlog.get_logger()


# Count of rate-limit (429 / "too many requests") failures seen by the metric fetchers; the scheduler batch reads it
# between chunks to back off instead of hammering a throttled API.
_RATE_LIMIT_HITS = 0


def _note_rate_limit(exc: BaseException) -> bool:
    """True (and counted) when an exception looks like an HTTP 429 / Google Trends throttle."""
    global _RATE_LIMIT_HITS
    msg = str(exc).lower()
    if "429" in msg or "too many requests" in msg or "rate limit" in msg:
        _RATE_LIMIT_HITS += 1
        return True
    return False


async def _fetch_lastfm_metrics(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch Last.fm metrics for one entity."""
    entity_name = entity["name"]

    # Try exact name first, fall back to search if no mbid stored
    async with LastFMClient() as client:
        results = await client.search_artist(entity_name, limit=1)

    if not results:
        return {}

    top_result = results[0]
    matched_name = top_result.get("name", entity_name)

    # Fetch full profile with the matched name
    async with LastFMClient() as client:
        artist = await client.get_artist_info(matched_name)

    return {
        "lastfm_mbid": artist.get("lastfm_mbid"),
        "lastfm_listeners": artist.get("listeners"),     # Monthly unique listeners
        "lastfm_playcount": artist.get("playcount"),    # All-time play count
        "lastfm_tags": artist.get("tags", []),          # Genre tags
        "lastfm_similar": artist.get("similar_artists", []),
    }


async def _fetch_youtube_metrics(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch YouTube channel metrics for one entity."""
    external_ids = entity.get("external_ids", {})
    channel_id = external_ids.get("youtube_channel_id")

    if not channel_id:
        async with YouTubeClient() as client:
            channels = await client.search_channel(entity["name"], max_results=1)
        if not channels:
            return {}
        channel_id = channels[0].get("youtube_channel_id")
        if not channel_id:
            return {}

    async with YouTubeClient() as client:
        stats = await client.get_channel_stats(channel_id)

    return {
        "youtube_channel_id": channel_id,
        "youtube_subscribers": stats.get("subscribers"),
        "youtube_total_views": stats.get("total_views"),
        "youtube_video_count": stats.get("video_count"),
    }


async def _fetch_google_trends(entity_name: str) -> Dict[str, Any]:
    """Fetch Google Trends score for one entity."""
    client = GoogleTrendsClient()
    result = await client.get_interest_over_time([entity_name], timeframe="today 1-m")
    interest_data = result.get("interest", {}).get(entity_name, [])

    if not interest_data:
        return {"google_trend_score": None, "google_trend_delta_7d": None}

    current_score = interest_data[-1] if interest_data else 0
    score_7d_ago = interest_data[-8] if len(interest_data) >= 8 else interest_data[0]
    delta_7d = (
        round(((current_score - score_7d_ago) / max(score_7d_ago, 1)) * 100, 1)
        if score_7d_ago
        else 0.0
    )

    return {
        "google_trend_score": float(current_score),
        "google_trend_delta_7d": delta_7d,
    }


_NEWSAPI_COOLDOWN_UNTIL = 0.0


async def _fetch_news_free(entity: Optional[Dict[str, Any]], entity_name: str) -> Optional[Dict[str, Any]]:
    """Keyless fallback (GDELT / Google News RSS). None when no source answered."""
    from app.services.ingestion.news_free_client import fetch_news_mentions
    e = entity or {}
    res = await fetch_news_mentions(entity_name, e.get("entity_type"), e.get("category"), bool(e.get("is_international")))
    if res is None:
        return None
    return {"news_mentions_7d": res.count, "news_source": res.provenance()}


async def _fetch_news_metrics(entity_name: str, entity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """News mention count (+ controversy risk when NewsAPI answers). Falls back automatically to the keyless
    GDELT / Google News source when NewsAPI is unconfigured, rate-limited (429) or returns no results."""
    import time as _time
    global _NEWSAPI_COOLDOWN_UNTIL
    newsapi: Optional[Dict[str, Any]] = None
    if _time.monotonic() >= _NEWSAPI_COOLDOWN_UNTIL:
        try:
            async with NewsAPIClient() as client:
                news = await client.search_entity_news(entity_name, days_back=7, page_size=10)
                controversy = await client.search_controversy(entity_name, days_back=30)
            newsapi = {
                "news_mentions_7d": news.get("total_results", 0),
                "controversy_risk": controversy.get("risk_level", "low"),
                "news_source": {"source": "newsapi", "retrieved": datetime.utcnow().date().isoformat(), "window_days": 7},
            }
        except Exception as exc:  # noqa: BLE001
            if _note_rate_limit(exc):
                _NEWSAPI_COOLDOWN_UNTIL = _time.monotonic() + 3600  # do not sleep through Retry-After for every entity
            logger.info("NewsAPI unavailable, using keyless news source", error=str(exc)[:120])
    if newsapi and newsapi["news_mentions_7d"]:
        return newsapi
    free = await _fetch_news_free(entity, entity_name)
    if free is not None and (free["news_mentions_7d"] or not newsapi):
        return {**(newsapi or {}), **free} if newsapi else free
    return newsapi or {}


async def _process_single_entity(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch all metrics for a single entity.
    Runs Spotify + YouTube concurrently, then Google Trends + News concurrently.
    """
    entity_name = entity["name"]
    entity_id = entity["id"]
    log = logger.bind(entity=entity_name, entity_id=str(entity_id))
    log.info("Starting metric collection")

    # Run first two concurrently (different APIs — no shared rate limits)
    lastfm_result, youtube_result = await asyncio.gather(
        _fetch_lastfm_metrics(entity),
        _fetch_youtube_metrics(entity),
        return_exceptions=True,
    )

    # Run second batch concurrently
    trends_result, news_result = await asyncio.gather(
        _fetch_google_trends(entity_name),
        _fetch_news_metrics(entity_name, entity),
        return_exceptions=True,
    )

    # Log any failures without crashing the whole task
    metrics = {"entity_id": entity_id, "collected_at": datetime.utcnow().isoformat()}
    data_sources = []

    if isinstance(lastfm_result, dict) and lastfm_result:
        metrics.update(lastfm_result)
        data_sources.append("lastfm")
    elif isinstance(lastfm_result, Exception):
        _note_rate_limit(lastfm_result)
        log.warning("Last.fm fetch failed", error=str(lastfm_result))

    if isinstance(youtube_result, dict) and youtube_result:
        metrics.update(youtube_result)
        data_sources.append("youtube")
    elif isinstance(youtube_result, Exception):
        _note_rate_limit(youtube_result)
        log.warning("YouTube fetch failed", error=str(youtube_result))

    if isinstance(trends_result, dict) and trends_result:
        metrics.update(trends_result)
        data_sources.append("google_trends")
    elif isinstance(trends_result, Exception):
        _note_rate_limit(trends_result)
        log.warning("Google Trends fetch failed", error=str(trends_result))

    if isinstance(news_result, dict) and news_result:
        metrics.update(news_result)
        data_sources.append("news")
    elif isinstance(news_result, Exception):
        log.warning("News fetch failed", error=str(news_result))

    metrics["data_completeness"] = len(data_sources) / 4.0
    metrics["data_sources"] = data_sources

    # Compute composite score
    composite_score = _compute_composite_score(metrics)
    metrics["composite_score"] = composite_score
    metrics["trend_direction"] = _compute_trend_direction(metrics)

    # Write to PostgreSQL
    await _write_metric_to_db(entity_id, metrics)

    log.info(
        "Metric collection complete",
        sources=data_sources,
        completeness=metrics["data_completeness"],
        composite_score=composite_score,
    )
    return metrics


def _compute_composite_score(metrics: Dict[str, Any]) -> Optional[float]:
    """Composite 0-100 score. Delegates to the pure, tested v2 formula in
    app/services/scoring/composite.py (log-scaled counts, weights renormalised
    over the signals that are present)."""
    from app.services.scoring.composite import compute_composite_score
    return compute_composite_score(metrics)


def _compute_trend_direction(metrics: Dict[str, Any]) -> str:
    """Determine trend direction from listener delta and trend delta."""
    delta = metrics.get("listener_delta_7d") or 0
    trend_delta = metrics.get("google_trend_delta_7d") or 0
    combined = (delta or 0) + (trend_delta or 0)
    if combined > 5:
        return "rising"
    elif combined < -5:
        return "falling"
    return "stable"


async def _write_metric_to_db(entity_id: Any, metrics: Dict[str, Any]) -> None:
    """Write collected metrics as a new EntityMetric row in PostgreSQL."""
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        metric = EntityMetric(
            entity_id=entity_id,
            time=now,
            # Last.fm — keys come from _fetch_lastfm_metrics
            lastfm_listeners=metrics.get("lastfm_listeners"),
            lastfm_weekly_plays=metrics.get("lastfm_playcount"),
            # YouTube
            youtube_subscribers=metrics.get("youtube_subscribers"),
            youtube_views_30d=metrics.get("youtube_views_30d"),
            youtube_subscriber_growth_7d=metrics.get("youtube_video_count"),  # repurposed temporarily
            # Google Trends
            google_trend_score=metrics.get("google_trend_score"),
            google_trend_delta_7d=metrics.get("google_trend_delta_7d"),
            # News
            news_mentions_7d=metrics.get("news_mentions_7d"),
            # Computed
            composite_score=metrics.get("composite_score"),
            data_completeness=metrics.get("data_completeness"),
            collection_source="entity_metrics_worker",
            signal_provenance=({"news_mentions_7d": metrics["news_source"]} if metrics.get("news_source") else None),
        )
        session.add(metric)
        try:
            # last_enriched_at drives entity_metrics' own "never scored yet"
            # priority ordering (see _sync_all) — without this update every
            # entity looks permanently unenriched and new discoveries would
            # never get bumped ahead of already-scored entities.
            await session.execute(
                update(Entity).where(Entity.id == entity_id).values(last_enriched_at=now)
            )
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("Failed to write metric to DB", entity_id=str(entity_id), error=str(e))


@celery_app.task(
    name="app.workers.entity_metrics.sync_all_active_entities",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def sync_all_active_entities(self: Task):
    """
    Main entry point: fetch Spotify, YouTube, Google Trends, and News
    metrics for all active entities in the database.
    """
    logger.info("entity_metrics: starting sync cycle")

    try:
        result = run_async(_sync_all())
        logger.info("entity_metrics: sync cycle complete", **result)
        return result
    except Exception as exc:
        logger.error("entity_metrics: sync cycle failed", error=str(exc))
        raise self.retry(exc=exc)


async def collect_entity_metrics_batch(limit: int = 60, chunk: int = 6, chunk_pause: float = 4.0,
                                       max_backoffs: int = 3) -> Dict[str, Any]:
    """Scheduler entry point (plain async, no Celery). Collects metrics for the `limit` entities whose newest
    collection is OLDEST (never-collected first), so every entity accumulates history over successive days.
    Concurrency 3 (semaphore); processed in small chunks with a pause, and when a chunk hit a 429/throttle the
    batch backs off exponentially (30s, 60s, 120s) and stops early after `max_backoffs` consecutive throttled chunks.
    """
    global _RATE_LIMIT_HITS
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Entity)
            .where(Entity.status == "active")
            .order_by(Entity.last_enriched_at.asc().nullsfirst(), Entity.name.asc())
            .limit(limit)
        )
        entities = [
            {"id": e.id, "name": e.name, "external_ids": e.external_ids or {},
             "entity_type": e.entity_type, "category": e.category,
             "is_international": e.is_international}
            for e in res.scalars().all()
        ]
    if not entities:
        return {"rows": 0, "status": "no_entities"}

    sem = asyncio.Semaphore(3)

    async def _one(e):
        async with sem:
            return await _process_single_entity(e)

    ok = failed = backoffs = 0
    stopped_early = False
    for i in range(0, len(entities), chunk):
        before = _RATE_LIMIT_HITS
        results = await asyncio.gather(*[_one(e) for e in entities[i:i + chunk]], return_exceptions=True)
        ok += sum(1 for r in results if not isinstance(r, Exception))
        failed += sum(1 for r in results if isinstance(r, Exception))
        if _RATE_LIMIT_HITS > before:
            backoffs += 1
            if backoffs >= max_backoffs:
                stopped_early = True
                logger.warning("entity_metrics batch: repeated rate limits, stopping early", done=ok)
                break
            wait = 30 * (2 ** (backoffs - 1))
            logger.warning("entity_metrics batch: rate limited, backing off", seconds=wait)
            await asyncio.sleep(wait)
        else:
            backoffs = 0
            await asyncio.sleep(chunk_pause)
    return {"rows": ok, "failed": failed, "selected": len(entities),
            "status": "partial_rate_limited" if stopped_early else "complete"}


ENTITIES_PER_CYCLE = 100  # Raised from 50 now that artist_discovery.py can add 100+ entities per run


async def _sync_all() -> Dict[str, Any]:
    """
    Fetch all active entities from PostgreSQL and process them.
    Uses a semaphore to limit concurrency (avoid hammering APIs).
    """
    async with AsyncSessionLocal() as session:
        # Entities that have NEVER been scored (last_enriched_at IS NULL —
        # true for every artist_discovery.py find) go first. Ordering by
        # is_active_on_district/is_verified alone (the original query) means
        # a newly discovered entity — always False on both — could never be
        # reached within the per-cycle cap once the roster grows past it,
        # since verified/on-district entities always sort ahead of it.
        result = await session.execute(
            select(Entity)
            .where(Entity.status == "active")
            .order_by(
                Entity.last_enriched_at.is_(None).desc(),
                Entity.is_active_on_district.desc(),
                Entity.is_verified.desc(),
            )
            .limit(ENTITIES_PER_CYCLE)
        )
        db_entities = result.scalars().all()

    entities = [
        {
            "id": e.id,
            "name": e.name,
            "external_ids": e.external_ids or {},
            "entity_type": e.entity_type,
            "category": e.category,
            "is_international": e.is_international,
        }
        for e in db_entities
    ]

    if not entities:
        logger.info("entity_metrics: no active entities in DB")
        return {"processed": 0, "status": "no_entities"}

    logger.info("entity_metrics: processing entities", count=len(entities))
    semaphore = asyncio.Semaphore(3)  # Max 3 entities concurrently

    async def _process_with_semaphore(entity):
        async with semaphore:
            return await _process_single_entity(entity)

    results = await asyncio.gather(
        *[_process_with_semaphore(e) for e in entities],
        return_exceptions=True,
    )

    success = sum(1 for r in results if not isinstance(r, Exception))
    failed = sum(1 for r in results if isinstance(r, Exception))

    logger.info(
        "entity_metrics: sync complete",
        total=len(entities),
        success=success,
        failed=failed,
    )
    return {
        "processed": success,
        "failed": failed,
        "total": len(entities),
        "status": "complete",
    }

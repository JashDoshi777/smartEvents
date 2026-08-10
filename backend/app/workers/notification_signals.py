"""
LiveIQ — Notification Signal Generator (Sprint 5D)
Detects breakout/news-buzz signals (same logic /dashboard/alerts uses to
compute on the fly) and persists them into TrendSignal so the notification
bell has stable IDs and real read/unread state.

This used to run inline inside the GET /notifications and
GET /notifications/unread-count route handlers. That was wrong: two reads
racing each other (e.g. the bell badge and the dropdown list loading a few
seconds apart) could each independently insert signals, so the badge count
and the list could observe different states depending on which read
happened to trigger generation last. Generation is now a single scheduled
job — routes only ever read/update, never generate.

Schedule: every 15 minutes (see celery_app.py beat_schedule)
"""

from datetime import datetime, timezone

import structlog
from celery import Task
from sqlalchemy import select, desc

from app.workers.celery_app import celery_app
from app.workers.run_utils import run_async
from app.core.database import AsyncSessionLocal
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.intelligence import TrendSignal

logger = structlog.get_logger()


async def _already_exists(db, entity_id, signal_type: str) -> bool:
    """
    True if an UNREAD signal of this type already exists for this entity,
    regardless of when it was detected. Dedup used to key off "created
    since today's midnight," which meant an ongoing, still-unread breakout
    would generate a fresh duplicate every day after midnight instead of
    being suppressed until the user actually reads the existing one.
    """
    result = await db.execute(
        select(TrendSignal.id).where(
            TrendSignal.entity_id == entity_id,
            TrendSignal.signal_type == signal_type,
            TrendSignal.is_read.is_(False),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _generate() -> dict:
    now = datetime.now(timezone.utc)
    created = 0
    failed = 0

    async with AsyncSessionLocal() as db:
        # ── Breakout signals: google trend outpacing composite score ──────
        breakout_result = await db.execute(
            select(Entity.id, Entity.name, EntityMetric.composite_score, EntityMetric.google_trend_score)
            .join(EntityMetric, Entity.id == EntityMetric.entity_id)
            .where(EntityMetric.google_trend_score.isnot(None), EntityMetric.composite_score.isnot(None))
            .order_by(desc(EntityMetric.google_trend_score))
            .limit(5)
        )
        for entity_id, name, score, trend in breakout_result.all():
            try:
                if not (trend and score and trend > score):
                    continue
                if await _already_exists(db, entity_id, "search_breakout"):
                    continue
                gap = round(trend - score, 1)
                # SAVEPOINT per row — a failure here only rolls back this
                # row, not every signal already added earlier in this cycle
                # (a plain db.rollback() would discard the whole session).
                async with db.begin_nested():
                    db.add(TrendSignal(
                        entity_id=entity_id,
                        signal_type="search_breakout",
                        current_value=trend,
                        previous_value=score,
                        delta_7d=gap,
                        severity="high",
                        alert_message=f"{name} showing breakout signals — Google Trend score ({trend}) exceeds composite ({score}) by +{gap} pts.",
                        detected_at=now,
                    ))
                    await db.flush()
                created += 1
            except Exception as exc:
                failed += 1
                logger.warning("notification_signals: breakout row failed", entity_id=str(entity_id), error=str(exc))

        # ── News buzz signals ──────────────────────────────────────────────
        news_result = await db.execute(
            select(Entity.id, Entity.name, EntityMetric.news_mentions_7d)
            .join(EntityMetric, Entity.id == EntityMetric.entity_id)
            .where(EntityMetric.news_mentions_7d.isnot(None), EntityMetric.news_mentions_7d > 0)
            .order_by(desc(EntityMetric.news_mentions_7d))
            .limit(3)
        )
        for entity_id, name, news in news_result.all():
            try:
                if await _already_exists(db, entity_id, "news_burst"):
                    continue
                async with db.begin_nested():
                    db.add(TrendSignal(
                        entity_id=entity_id,
                        signal_type="news_burst",
                        current_value=float(news),
                        severity="medium",
                        alert_message=f"{name} in the news — {news} mentions in the last 7 days.",
                        detected_at=now,
                    ))
                    await db.flush()
                created += 1
            except Exception as exc:
                failed += 1
                logger.warning("notification_signals: news row failed", entity_id=str(entity_id), error=str(exc))

        await db.commit()

    return {"created": created, "failed": failed, "ran_at": now.isoformat()}


@celery_app.task(
    name="app.workers.notification_signals.generate_notification_signals",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def generate_notification_signals(self: Task):
    """Entry point: detect and persist notification signals. Runs every 15 min."""
    logger.info("notification_signals: starting generation cycle")
    try:
        result = run_async(_generate())
        logger.info("notification_signals: generation complete", **result)
        return result
    except Exception as exc:
        logger.error("notification_signals: generation failed", error=str(exc))
        raise self.retry(exc=exc)

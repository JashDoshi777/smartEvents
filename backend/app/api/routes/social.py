"""
LiveIQ — Social Listening Routes (M7)
Real DB-backed sentiment, topics, and crisis alerts — sourced from
SocialPost (individual real Reddit/News items, VADER-scored) and
EntityMetric (aggregate sentiment/mention counts), both written by
app/workers/social_listening.py. Previously these three endpoints were
pure stubs (empty dicts/lists, "message": "... Sprint 4 ML") backed by
a worker whose entity list was hardcoded to []; the worker now runs for
real, so these routes read real, if possibly sparse, data instead of
permanently empty placeholders.

Endpoints:
  GET /social/sentiment/{entity_id}  → real sentiment breakdown + recent posts
  GET /social/topics/{entity_id}     → real keyword-based theme counts (no ML —
                                        per ENGINEERING_PLAYBOOK.md's own M7
                                        spec: "Simple keyword counting — no ML
                                        needed for this")
  GET /social/crisis-alerts          → entities with a real negative-sentiment
                                        spike in the last 24h vs the prior 7 days
"""

from datetime import datetime, timedelta, timezone
from typing import Dict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.intelligence import SocialPost
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()

# Same real keyword-topic map ENGINEERING_PLAYBOOK.md's M7 section specifies
# verbatim ("Simple keyword counting — no ML needed for this") — kept as
# plain substring matching against real SocialPost content, not a
# fabricated NLP classifier.
TOPICS = {
    "parking": ["parking", "traffic", "car park"],
    "queues": ["queue", "wait", "line", "slow entry"],
    "sound": ["sound", "audio", "bass", "echo", "mic"],
    "pricing": ["expensive", "overpriced", "costly", "ticket price"],
    "performance": ["amazing", "brilliant", "incredible", "energy", "electric"],
    "venue": ["venue", "seating", "view", "screen", "stage"],
    "security": ["security", "safety", "crowd control", "checkpoint"],
}


@router.get("/sentiment/{entity_id}", summary="Real sentiment breakdown for an entity")
async def get_entity_sentiment(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = await db.scalar(select(Entity).where(Entity.id == uid))
    if entity is None:
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    # Latest aggregate — written by social_listening.py each cycle it ran for this entity.
    latest_metric = await db.scalar(
        select(EntityMetric)
        .where(EntityMetric.entity_id == uid, EntityMetric.sentiment_sample_size.isnot(None))
        .order_by(desc(EntityMetric.time))
        .limit(1)
    )

    # Real recent individual posts, for a "here's what people actually said" view.
    recent_posts_result = await db.execute(
        select(SocialPost)
        .where(SocialPost.entity_id == uid)
        .order_by(desc(SocialPost.analyzed_at))
        .limit(10)
    )
    recent_posts = recent_posts_result.scalars().all()

    if latest_metric is None and not recent_posts:
        return {
            "entity_id": entity_id,
            "entity_name": entity.name,
            "sentiment": {},
            "recent_posts": [],
            "status": "no_data_yet",
            "message": "No social listening data collected yet for this entity. The worker runs every 30 minutes and only covers a rotating priority subset of entities per cycle.",
        }

    return {
        "entity_id": entity_id,
        "entity_name": entity.name,
        "sentiment": {
            "positive": latest_metric.sentiment_positive if latest_metric else None,
            "negative": latest_metric.sentiment_negative if latest_metric else None,
            "neutral": latest_metric.sentiment_neutral if latest_metric else None,
            "compound": latest_metric.sentiment_compound if latest_metric else None,
            "sample_size": latest_metric.sentiment_sample_size if latest_metric else None,
            "reddit_posts_7d": latest_metric.reddit_posts_7d if latest_metric else None,
            "news_mentions_7d": latest_metric.news_mentions_7d if latest_metric else None,
            "last_collected_at": latest_metric.time.isoformat() if latest_metric else None,
        },
        "recent_posts": [
            {
                "platform": p.platform,
                "content_snippet": p.content_snippet,
                "sentiment_label": p.sentiment_label,
                "sentiment_score": p.sentiment_score,
                "likes": p.likes,
                "comments": p.comments,
                "analyzed_at": p.analyzed_at.isoformat() if p.analyzed_at else None,
            }
            for p in recent_posts
        ],
        "status": "ok",
    }


@router.get("/topics/{entity_id}", summary="Real keyword-based topic counts from collected posts")
async def get_trending_topics(
    entity_id: str,
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = await db.scalar(select(Entity).where(Entity.id == uid))
    if entity is None:
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    since = datetime.now(timezone.utc) - timedelta(days=days)
    posts_result = await db.execute(
        select(SocialPost.content_snippet)
        .where(SocialPost.entity_id == uid, SocialPost.analyzed_at >= since)
    )
    snippets = [row[0] or "" for row in posts_result.all()]

    topic_counts: Dict[str, int] = {t: 0 for t in TOPICS}
    for snippet in snippets:
        text_lower = snippet.lower()
        for topic, keywords in TOPICS.items():
            if any(kw in text_lower for kw in keywords):
                topic_counts[topic] += 1

    topics = [
        {"topic": t, "mentions": c}
        for t, c in sorted(topic_counts.items(), key=lambda kv: kv[1], reverse=True)
        if c > 0
    ]

    return {
        "entity_id": entity_id,
        "entity_name": entity.name,
        "topics": topics,
        "total_posts_analyzed": len(snippets),
        "window_days": days,
        "methodology": "Keyword substring matching against real collected post/article snippets — no ML classifier.",
    }


@router.get("/crisis-alerts", summary="Entities with a real negative-sentiment spike")
async def get_crisis_alerts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Real spike detection: for each entity with social data, compares the
    negative-post share in the last 24h against the prior 7 days. Flags
    entities where negative share rose by >=20 percentage points AND at
    least 3 posts were collected in the last 24h (avoids flagging a
    single angry post as a "spike" off a tiny sample).
    """
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    prior_7d_start = now - timedelta(days=8)  # the 7 days BEFORE the last 24h window

    async def _negative_share(entity_id, start, end) -> tuple[float, int]:
        result = await db.execute(
            select(SocialPost.sentiment_label)
            .where(SocialPost.entity_id == entity_id, SocialPost.analyzed_at >= start, SocialPost.analyzed_at < end)
        )
        labels = [row[0] for row in result.all()]
        if not labels:
            return 0.0, 0
        negative = sum(1 for l in labels if l == "negative")
        return negative / len(labels), len(labels)

    # Entities with ANY social data at all, to scope the scan to real coverage.
    entities_result = await db.execute(
        select(Entity.id, Entity.name).join(SocialPost, SocialPost.entity_id == Entity.id).distinct()
    )
    entities = entities_result.all()

    alerts = []
    for entity_id, entity_name in entities:
        recent_share, recent_count = await _negative_share(entity_id, last_24h, now)
        baseline_share, baseline_count = await _negative_share(entity_id, prior_7d_start, last_24h)

        if recent_count < 3:
            continue  # too little data in the last 24h to call this a real spike

        delta = recent_share - baseline_share
        if delta >= 0.20:
            severity = "critical" if delta >= 0.50 else ("high" if delta >= 0.35 else "medium")
            alerts.append({
                "entity_id": str(entity_id),
                "entity_name": entity_name,
                "severity": severity,
                "negative_share_last_24h": round(recent_share, 2),
                "negative_share_prior_7d": round(baseline_share, 2),
                "delta_pct_points": round(delta * 100, 1),
                "posts_last_24h": recent_count,
                "posts_prior_7d": baseline_count,
            })

    alerts.sort(key=lambda a: a["delta_pct_points"], reverse=True)

    return {
        "alerts": alerts,
        "total": len(alerts),
        "methodology": "Negative-sentiment share in the last 24h vs the prior 7 days, per entity — flagged at >=20 percentage point increase with >=3 posts in the last 24h.",
    }

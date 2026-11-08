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
from sqlalchemy import case, func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, run_queries
from app.services.market_scope import Market, market_clause
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

    # Latest aggregate row that actually carries sentiment (written by the
    # social-listening worker) + recent real posts + the entity, in parallel.
    entity_rows, metric_rows, post_rows = await run_queries(
        select(Entity).where(Entity.id == uid),
        select(EntityMetric)
        .where(EntityMetric.entity_id == uid, EntityMetric.sentiment_sample_size.isnot(None))
        .order_by(desc(EntityMetric.time)).limit(1),
        select(SocialPost).where(SocialPost.entity_id == uid).order_by(desc(SocialPost.analyzed_at)).limit(10),
    )
    if not entity_rows:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    entity = entity_rows[0][0]
    latest_metric = metric_rows[0][0] if metric_rows else None
    recent_posts = [r[0] for r in post_rows]

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

    since = datetime.now(timezone.utc) - timedelta(days=days)
    entity_rows, post_rows = await run_queries(
        select(Entity).where(Entity.id == uid),
        select(SocialPost.content_snippet).where(SocialPost.entity_id == uid, SocialPost.analyzed_at >= since),
    )
    if not entity_rows:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    entity = entity_rows[0][0]
    snippets = [row[0] or "" for row in post_rows]

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
    market: Market = "all",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Spike detection in ONE grouped query (was 2 queries per entity): compares
    the negative-post share in the last 24h against the prior 7 days and flags
    entities where it rose >=20 percentage points AND >=3 posts were collected
    in the last 24h (a single angry post off a tiny sample is not a spike).
    """
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    prior_start = now - timedelta(days=8)  # the 7 days BEFORE the last 24h window

    recent = (SocialPost.analyzed_at >= last_24h) & (SocialPost.analyzed_at < now)
    prior = (SocialPost.analyzed_at >= prior_start) & (SocialPost.analyzed_at < last_24h)
    neg = SocialPost.sentiment_label == "negative"
    stmt = (
        select(
            Entity.id, Entity.name,
            func.count().filter(recent), func.count().filter(recent & neg),
            func.count().filter(prior), func.count().filter(prior & neg),
        )
        .join(SocialPost, SocialPost.entity_id == Entity.id)
        .where(market_clause(market), SocialPost.analyzed_at >= prior_start)
        .group_by(Entity.id, Entity.name)
        .having(func.count().filter(recent) >= 3)
    )
    (rows,) = await run_queries(stmt)

    alerts = []
    for entity_id, entity_name, r_total, r_neg, b_total, b_neg in rows:
        recent_share = r_neg / r_total if r_total else 0.0
        baseline_share = b_neg / b_total if b_total else 0.0
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
                "posts_last_24h": r_total,
                "posts_prior_7d": b_total,
            })

    alerts.sort(key=lambda a: (-a["delta_pct_points"], a["entity_name"]))
    return {
        "alerts": alerts,
        "total": len(alerts),
        "market": market,
        "methodology": "Negative-sentiment share in the last 24h vs the prior 7 days, per entity — flagged at >=20 percentage point increase with >=3 posts in the last 24h.",
    }


@router.get("/sampled", summary="Entities that actually have social data (most posts first)")
async def get_sampled_entities(
    market: Market = "all",
    limit: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One grouped query replacing N per-entity sentiment probes from the client."""
    rows = (await db.execute(
        select(Entity.id, Entity.name, func.count(SocialPost.id).label("n"))
        .join(SocialPost, SocialPost.entity_id == Entity.id)
        .where(market_clause(market), Entity.status == "active")
        .group_by(Entity.id, Entity.name)
        .order_by(desc("n"))
        .limit(limit)
    )).all()
    return {"entities": [{"entity_id": str(r[0]), "entity_name": r[1], "posts": r[2]} for r in rows], "total": len(rows)}

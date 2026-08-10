"""
LiveIQ — Social Listening Worker (M7)
Collects real Reddit mentions and News sentiment for active entities,
scores each individual post/article with VADER (real NLP, no training
data needed — matches ENGINEERING_PLAYBOOK.md's M7 spec), persists
per-item results to SocialPost (for topic/crisis drill-down) and an
aggregate to EntityMetric (sentiment_positive/negative/compound,
reddit_posts_7d, news_mentions_7d — feeding the same columns
entity_metrics.py's composite score already reads from, so this data
is visible everywhere that already renders EntityMetric, not just in
new /social/* routes).

Previously this worker's entity list was a hardcoded empty list
(`stub_entities: List[Dict[str, Any]] = []`) — it never actually ran
against anything, despite being scheduled every 30 minutes. Now reuses
the exact same "active, priority-ordered" entity query
entity_metrics.py's _sync_all() uses, so the same entities that get
Spotify/YouTube/Trends metrics also get social listening.

Schedule: every 30 minutes (see celery_app.py beat_schedule)
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog
from celery import Task
from sqlalchemy import select, update
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.workers.celery_app import celery_app
from app.workers.run_utils import run_async
from app.core.database import AsyncSessionLocal
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.intelligence import SocialPost
from app.services.ingestion.reddit_client import RedditClient
from app.services.ingestion.newsapi_client import NewsAPIClient

logger = structlog.get_logger()
_vader = SentimentIntensityAnalyzer()

ENTITIES_PER_CYCLE = 30  # smaller than entity_metrics.py's 100 — Reddit/NewsAPI have tighter rate limits
CONCURRENCY = 5           # Reddit's real rate limit is the binding constraint


def _sentiment_label(compound: float) -> str:
    if compound > 0.05:
        return "positive"
    if compound < -0.05:
        return "negative"
    return "neutral"


async def _get_priority_entities() -> List[Dict[str, Any]]:
    """
    Same real "never-covered-first, then on-District, then verified"
    ordering entity_metrics.py's _sync_all() uses, applied to this
    worker's OWN last_social_listened_at column — not the shared
    last_enriched_at column entity_metrics.py uses for its own priority
    ordering, since the two workers running on independent schedules
    against a shared timestamp field would each make entities look
    "already handled" to the other, starving whichever worker didn't
    touch an entity first.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Entity)
            .where(Entity.status == "active")
            .order_by(
                Entity.last_social_listened_at.is_(None).desc(),
                Entity.is_active_on_district.desc(),
                Entity.is_verified.desc(),
            )
            .limit(ENTITIES_PER_CYCLE)
        )
        entities = result.scalars().all()
        return [{"id": e.id, "name": e.name} for e in entities]


async def _collect_reddit_mentions(entity_name: str) -> Dict[str, Any]:
    """Collect real Reddit mentions for an entity, scored per-post with VADER."""
    async with RedditClient() as client:
        result = await client.get_india_artist_mentions(entity_name, days=7)

    posts = result.get("top_posts", [])
    scored_posts = []
    for p in posts:
        text = f"{p.get('title', '')} {p.get('selftext', '')}".strip()
        if not text:
            continue
        scores = _vader.polarity_scores(text)
        scored_posts.append({**p, "vader": scores})

    return {
        "reddit_posts_7d": result.get("mentions", 0),
        # Real total upvotes across this cycle's top posts — EntityMetric's
        # own reddit_upvotes_7d column, previously left unpopulated even
        # though the real per-post "score" (upvotes) field was already
        # being fetched and just discarded.
        "reddit_upvotes_7d": sum(p.get("score", 0) for p in posts),
        "reddit_avg_score": result.get("avg_score", 0),
        "reddit_top_post_score": result.get("max_score", 0),
        "reddit_total_comments": result.get("total_comments", 0),
        "reddit_subreddits": result.get("subreddits_found", []),
        "scored_posts": scored_posts,
    }


async def _collect_news_sentiment(entity_name: str) -> Dict[str, Any]:
    """Collect real recent news, scored per-article with VADER, plus real controversy risk."""
    async with NewsAPIClient() as client:
        news_result, controversy_result = await asyncio.gather(
            client.search_entity_news(entity_name, days_back=7, page_size=20),
            client.search_controversy(entity_name, days_back=14),
            return_exceptions=True,
        )

    result: Dict[str, Any] = {"scored_articles": []}
    if isinstance(news_result, dict):
        result["news_mentions_7d"] = news_result.get("total_results", 0)
        for a in news_result.get("articles", []):
            text = f"{a.get('title', '')} {a.get('description', '')}".strip()
            if not text:
                continue
            scores = _vader.polarity_scores(text)
            result["scored_articles"].append({**a, "vader": scores})
        # EntityMetric.news_sentiment_7d is specifically the news-only
        # sentiment average (distinct from the combined reddit+news
        # sentiment_compound written elsewhere) — real if any articles
        # were scored, absent (not zero) otherwise.
        if result["scored_articles"]:
            result["news_sentiment_7d"] = round(
                sum(a["vader"]["compound"] for a in result["scored_articles"]) / len(result["scored_articles"]), 3
            )
    if isinstance(controversy_result, dict):
        result["controversy_risk"] = controversy_result.get("risk_level", "low")
        result["controversy_count_30d"] = controversy_result.get("controversy_article_count", 0)

    return result


async def _persist_social_posts(entity_id, reddit_posts: List[Dict], news_articles: List[Dict]) -> int:
    """Writes real per-item posts/articles to SocialPost — powers topic/crisis drill-down routes."""
    written = 0
    async with AsyncSessionLocal() as session:
        for p in reddit_posts:
            vader = p["vader"]
            session.add(SocialPost(
                entity_id=entity_id,
                platform="reddit",
                post_id=p.get("reddit_id"),
                content_snippet=(p.get("title") or "")[:500],
                sentiment_score=vader["compound"],
                sentiment_label=_sentiment_label(vader["compound"]),
                likes=p.get("score", 0),
                comments=p.get("num_comments", 0),
                posted_at=datetime.fromtimestamp(p["created_utc"], tz=timezone.utc) if p.get("created_utc") else None,
            ))
            written += 1
        for a in news_articles:
            vader = a["vader"]
            session.add(SocialPost(
                entity_id=entity_id,
                platform="news",
                post_id=a.get("url"),
                content_snippet=(a.get("title") or "")[:500],
                sentiment_score=vader["compound"],
                sentiment_label=_sentiment_label(vader["compound"]),
            ))
            written += 1
        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.warning("social_listening: SocialPost write failed", error=str(exc), entity_id=str(entity_id))
            return 0
    return written


async def _write_aggregate_metric(entity_id, aggregate: Dict[str, Any]) -> None:
    """
    Writes one aggregate EntityMetric row per cycle — same insert-per-
    cycle pattern entity_metrics.py's _write_metric_to_db uses. Only the
    social-relevant columns are populated; this does NOT touch
    composite_score (entity_metrics.py's 4-source weighting owns that —
    adding a 5th signal there is a deliberate decision this worker
    doesn't make unilaterally).
    """
    async with AsyncSessionLocal() as session:
        metric = EntityMetric(
            entity_id=entity_id,
            time=datetime.now(timezone.utc),
            reddit_posts_7d=aggregate.get("reddit_posts_7d"),
            reddit_upvotes_7d=aggregate.get("reddit_upvotes_7d"),
            reddit_comments_7d=aggregate.get("reddit_total_comments"),
            news_mentions_7d=aggregate.get("news_mentions_7d"),
            news_sentiment_7d=aggregate.get("news_sentiment_7d"),
            sentiment_positive=aggregate.get("sentiment_positive"),
            sentiment_negative=aggregate.get("sentiment_negative"),
            sentiment_neutral=aggregate.get("sentiment_neutral"),
            sentiment_compound=aggregate.get("sentiment_compound"),
            sentiment_sample_size=aggregate.get("sentiment_sample_size"),
            collection_source="social_listening_worker",
        )
        session.add(metric)
        try:
            await session.execute(
                update(Entity).where(Entity.id == entity_id).values(last_social_listened_at=datetime.now(timezone.utc))
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.warning("social_listening: EntityMetric write failed", error=str(exc), entity_id=str(entity_id))


async def _collect_for_entity(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Collect + score + persist social signals for one entity."""
    entity_id = entity["id"]
    entity_name = entity["name"]
    log = logger.bind(entity=entity_name)

    reddit_result, news_result = await asyncio.gather(
        _collect_reddit_mentions(entity_name),
        _collect_news_sentiment(entity_name),
        return_exceptions=True,
    )

    reddit_posts: List[Dict] = []
    news_articles: List[Dict] = []
    aggregate: Dict[str, Any] = {}

    if isinstance(reddit_result, dict):
        aggregate.update({k: v for k, v in reddit_result.items() if k != "scored_posts"})
        reddit_posts = reddit_result.get("scored_posts", [])
        log.debug("Reddit signals collected", mentions=reddit_result.get("reddit_posts_7d"))
    else:
        log.warning("Reddit collection failed (Reddit likely not configured — degrading gracefully)", error=str(reddit_result))

    if isinstance(news_result, dict):
        aggregate.update({k: v for k, v in news_result.items() if k != "scored_articles"})
        news_articles = news_result.get("scored_articles", [])
        log.debug("News signals collected", mentions=news_result.get("news_mentions_7d"))
    else:
        log.warning("News collection failed", error=str(news_result))

    # Real aggregate sentiment across every scored post+article this cycle
    # found for this entity — not fabricated, and explicitly absent (None)
    # when zero real items were scored, rather than defaulting to a
    # fake-neutral 0.
    all_scores = [p["vader"] for p in reddit_posts] + [a["vader"] for a in news_articles]
    if all_scores:
        n = len(all_scores)
        aggregate["sentiment_positive"] = round(sum(s["pos"] for s in all_scores) / n, 3)
        aggregate["sentiment_negative"] = round(sum(s["neg"] for s in all_scores) / n, 3)
        aggregate["sentiment_neutral"] = round(sum(s["neu"] for s in all_scores) / n, 3)
        aggregate["sentiment_compound"] = round(sum(s["compound"] for s in all_scores) / n, 3)
        aggregate["sentiment_sample_size"] = n

    posts_written = await _persist_social_posts(entity_id, reddit_posts, news_articles)
    await _write_aggregate_metric(entity_id, aggregate)

    return {
        "entity_id": str(entity_id),
        "entity_name": entity_name,
        "posts_written": posts_written,
        "has_reddit": bool(reddit_posts) or isinstance(reddit_result, dict),
        "has_news": bool(news_articles) or isinstance(news_result, dict),
    }


async def _collect_all_social() -> Dict[str, Any]:
    entities = await _get_priority_entities()
    if not entities:
        logger.info("social_listening: no active entities found")
        return {"processed": 0, "status": "no_entities"}

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def _bounded(entity):
        async with semaphore:
            return await _collect_for_entity(entity)

    results = await asyncio.gather(*[_bounded(e) for e in entities], return_exceptions=True)

    success = sum(1 for r in results if not isinstance(r, Exception))
    failed = sum(1 for r in results if isinstance(r, Exception))
    total_posts = sum(r["posts_written"] for r in results if isinstance(r, dict))

    return {
        "processed": success,
        "failed": failed,
        "total_entities": len(entities),
        "total_posts_written": total_posts,
        "status": "complete",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(
    name="app.workers.social_listening.collect_social_mentions",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def collect_social_mentions(self: Task):
    """Main entry: collect real Reddit + News mentions every 30 minutes."""
    logger.info("social_listening: starting collection cycle")
    try:
        result = run_async(_collect_all_social())
        logger.info("social_listening: collection complete", **result)
        return result
    except Exception as exc:
        logger.error("social_listening: collection failed", error=str(exc))
        raise self.retry(exc=exc)

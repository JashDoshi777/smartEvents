"""
LiveIQ — Artist Pairing Recommender (Sprint 6B)
Given a city + budget, suggests which two already-tracked artists would
share a bill well: genre-compatible AND similar popularity tier (cosine
similarity on real composite/trend/sentiment score vectors) — not just
"most similar numerically," which could pair a global superstar with an
unrelated genre's niche opener.

Endpoint:
  POST /intelligence/pair-recommend
"""

import asyncio
from typing import Optional
from uuid import UUID

import structlog
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.services.ingestion.lastfm_client import LastFMClient
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()
logger = structlog.get_logger()

# Score vector features used for cosine similarity — real signals already
# collected by entity_metrics.py, normalized to comparable ranges below.
VECTOR_FEATURES = ["composite_score", "google_trend_score", "sentiment_compound", "news_mentions_7d"]
NEWS_NORM_CAP = 200.0  # news_mentions_7d rarely exceeds this; used to scale into 0-100 range
COMPOSITE_SCORE_CAP = 100.0  # observed range is ~0-83; used to normalize the tier-distance term
MIN_GENRE_OVERLAP = 1  # at least one shared genre tag to be considered "compatible"


class PairRecommendRequest(BaseModel):
    city: str = Field(..., description="City where the event will be held (used for context only, no filtering yet)")
    budget: Optional[float] = Field(None, description="Combined booking budget (INR) — filters out pairs exceeding it")
    anchor_entity_id: Optional[str] = Field(None, description="If given, find the best pairing partner for this specific artist instead of ranking all pairs")
    market: Optional[str] = Field(None, description="Filter candidates to 'India' or 'Global' primary_market")
    limit: int = Field(5, ge=1, le=20)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _pairing_score(v1: np.ndarray, v2: np.ndarray) -> float:
    """
    Cosine similarity alone is scale-invariant: two artists with
    composite_score 0.3 and 1.44 (a 5x popularity-tier gap) score a
    perfect 1.0 if it's their only non-zero feature, since cosine only
    compares direction, not magnitude. Most entities currently have zero
    sentiment/trend/news signal (external APIs rate-limited or not yet
    backfilled), so composite_score dominates the vector — meaning
    magnitude IS the signal that matters here.

    composite_score is heavily right-skewed (median ~16, p90 ~39, but
    many niche artists sit in the 0.1-2 range) — an absolute-difference
    penalty is nearly zero for two niche artists 5x apart, since both
    are tiny numbers. Compare on a log scale instead so a 5x relative
    gap is penalized the same whether it's 0.3-to-1.5 or 15-to-75.
    """
    cosine = _cosine_similarity(v1, v2)
    log1 = np.log1p(max(v1[0], 0.0))
    log2 = np.log1p(max(v2[0], 0.0))
    log_cap = np.log1p(COMPOSITE_SCORE_CAP)
    tier_gap = abs(log1 - log2) / log_cap
    tier_closeness = max(0.0, 1.0 - tier_gap)
    return 0.5 * cosine + 0.5 * tier_closeness


def _to_vector(metric: EntityMetric) -> np.ndarray:
    composite = metric.composite_score or 0.0
    trend = metric.google_trend_score or 0.0
    sentiment = ((metric.sentiment_compound or 0.0) + 1) * 50  # -1..1 -> 0..100
    news = min((metric.news_mentions_7d or 0) / NEWS_NORM_CAP, 1.0) * 100
    return np.array([composite, trend, sentiment, news])


def _stored_genres(entity: Entity) -> Optional[set[str]]:
    """Real genres already on the row — no lookup needed."""
    if entity.genres:
        return {g.lower() for g in entity.genres}
    if entity.genre:
        return {entity.genre.lower()}
    return None


async def _fetch_and_persist_genres(db: AsyncSession, entities: list[Entity], client: LastFMClient) -> dict[str, set[str]]:
    """
    Auto-discovered entities (artist_discovery.py) have no stored genre,
    so this looks them up via Last.fm — but does so CONCURRENTLY (bounded
    by LastFMClient's own semaphore, RATE_LIMIT=5) instead of one-at-a-time
    inside the O(n) pairing loop, which serialized ~150 sequential network
    calls into a 2+ minute response. Results are written back to
    Entity.genres so future requests skip the lookup entirely for this
    artist.
    """
    missing = [e for e in entities if _stored_genres(e) is None]
    if not missing:
        return {}

    async def lookup(entity: Entity) -> tuple[Entity, set[str]]:
        try:
            tags = await client.get_artist_tags(entity.name)
        except Exception as exc:
            logger.warning("pair_recommend: tag lookup failed", entity=entity.name, error=str(exc))
            tags = []
        return entity, {t.lower() for t in tags}

    results = await asyncio.gather(*(lookup(e) for e in missing))

    fetched: dict[str, set[str]] = {}
    for entity, tags in results:
        fetched[str(entity.id)] = tags
        if tags:
            await db.execute(update(Entity).where(Entity.id == entity.id).values(genres=sorted(tags)))
    if any(tags for _, tags in results):
        await db.commit()

    return fetched


@router.post("/pair-recommend", summary="Recommend artist pairings for a shared bill")
async def recommend_pairs(
    request: PairRecommendRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Entity, EntityMetric)
        .join(EntityMetric, Entity.id == EntityMetric.entity_id)
        .where(Entity.status == "active", Entity.entity_type == "artist")
        .order_by(desc(EntityMetric.time))
    )
    if request.market:
        stmt = stmt.where(Entity.primary_market == request.market)

    result = await db.execute(stmt)
    rows = result.all()

    # Dedup to latest metric per entity (same pattern as executive.py's portfolio dedup)
    latest: dict[str, tuple[Entity, EntityMetric]] = {}
    for entity, metric in rows:
        key = str(entity.id)
        if key not in latest or (metric.time and latest[key][1].time and metric.time > latest[key][1].time):
            latest[key] = (entity, metric)

    candidates = list(latest.values())
    if len(candidates) < 2:
        raise HTTPException(400, "Not enough entities with live metrics to form a pairing. Run the entity_metrics worker first.")

    anchor: Optional[tuple[Entity, EntityMetric]] = None
    if request.anchor_entity_id:
        try:
            anchor_uid = UUID(request.anchor_entity_id)
        except ValueError:
            raise HTTPException(400, "Invalid anchor_entity_id format")
        anchor = latest.get(str(anchor_uid))
        if not anchor:
            raise HTTPException(404, f"Entity '{request.anchor_entity_id}' not found or has no live metrics yet")

    pool = [anchor] if anchor else candidates
    others = candidates

    # Skip constructing the Last.fm client entirely when every candidate
    # already has a stored genre — avoids an unhandled failure (e.g. missing
    # LASTFM_API_KEY) taking down the whole endpoint on a request that never
    # actually needed a live lookup.
    needs_lookup = any(_stored_genres(e) is None for e, _ in others)
    fetched: dict[str, set[str]] = {}
    if needs_lookup:
        try:
            async with LastFMClient() as client:
                fetched = await _fetch_and_persist_genres(db, [e for e, _ in others], client)
        except Exception as exc:
            logger.warning("pair_recommend: Last.fm client unavailable, proceeding without live genre lookup", error=str(exc))

    genre_cache: dict[str, set[str]] = {}

    def genres_for(entity: Entity) -> set[str]:
        key = str(entity.id)
        if key in genre_cache:
            return genre_cache[key]
        stored = _stored_genres(entity)
        result = stored if stored is not None else fetched.get(key, set())
        genre_cache[key] = result
        return result

    pairs = []

    for e1, m1 in pool:
        g1 = genres_for(e1)
        v1 = _to_vector(m1)
        for e2, m2 in others:
            if e1.id == e2.id:
                continue
            if anchor is None and e2.id < e1.id:
                continue  # avoid duplicate (A,B)/(B,A) pairs when ranking all pairs

            g2 = genres_for(e2)
            overlap = g1 & g2
            if len(overlap) < MIN_GENRE_OVERLAP:
                continue

            if request.budget is not None:
                fee1_mid = ((e1.booking_price_range_min or 0) + (e1.booking_price_range_max or 0)) / 2
                fee2_mid = ((e2.booking_price_range_min or 0) + (e2.booking_price_range_max or 0)) / 2
                combined_fee = fee1_mid + fee2_mid
                if combined_fee > 0 and combined_fee > request.budget:
                    continue

            v2 = _to_vector(m2)
            similarity = _pairing_score(v1, v2)

            pairs.append({
                "entity_a": {"id": str(e1.id), "name": e1.name, "category": e1.category, "composite_score": m1.composite_score},
                "entity_b": {"id": str(e2.id), "name": e2.name, "category": e2.category, "composite_score": m2.composite_score},
                "shared_genres": sorted(overlap),
                "similarity_score": round(similarity * 100, 1),
                "combined_booking_fee_estimate": (
                    round(((e1.booking_price_range_min or 0) + (e1.booking_price_range_max or 0)) / 2 +
                          ((e2.booking_price_range_min or 0) + (e2.booking_price_range_max or 0)) / 2)
                    if (e1.booking_price_range_min or e2.booking_price_range_min) else None
                ),
            })

    pairs.sort(key=lambda p: p["similarity_score"], reverse=True)
    top_pairs = pairs[: request.limit]

    return {
        "city": request.city,
        "budget": request.budget,
        "anchor_entity": {"id": str(anchor[0].id), "name": anchor[0].name} if anchor else None,
        "candidates_considered": len(candidates),
        "pairs_matching_genre": len(pairs),
        "recommendations": top_pairs,
        "methodology": (
            "Filtered to pairs sharing at least one genre tag (real Entity.genres, "
            "or a live Last.fm tag lookup for entities discovered via artist_discovery.py "
            "that have no stored genre), then ranked by a 50/50 blend of cosine similarity "
            f"on [{', '.join(VECTOR_FEATURES)}] (profile shape) and composite_score "
            "closeness (popularity-tier match) — real signals, not fabricated. The tier "
            "term matters because cosine similarity alone is scale-invariant and would call "
            "a niche opener and a headliner '100% compatible' whenever trend/sentiment/news "
            "data is sparse."
        ),
    }

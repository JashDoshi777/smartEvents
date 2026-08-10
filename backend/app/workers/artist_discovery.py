"""
LiveIQ — Artist Auto-Discovery Worker
=====================================
Closes a real gap: the entity roster was 100% hand-seeded (51 fixed names
in scripts/seed_entities.py) with no mechanism to notice a new or breaking
artist that isn't already in that list. Every scoring/breakout/notification
feature only ever re-evaluates entities that are already tracked — if an
artist blows up today and isn't one of the 51, LiveIQ has no way to see it.

Two tracks, deliberately asymmetric (product decision: Global = broad,
India = deep — District books major international tours, so global chart
noise is acceptable, but the India side needs to go beyond one chart since
that's the actual booking market):

  GLOBAL — Last.fm's global top-artists chart, taken as-is (any genre).
  Tagged primary_market="Global".

  INDIA  — three real signals, not just one chart:
    1. Last.fm's India-specific top-artists chart.
    2. Similar-artist expansion: for each entity already known to be
       India-relevant (existing entities with primary_market="India", or
       the newly-found India-chart names), pull Last.fm's real
       "similar artists" graph to surface India-adjacent names the India
       chart alone wouldn't (e.g. an artist popular in Punjabi-pop
       circles but not top-100 nationally).
  Tagged primary_market="India".

Both tracks create real Entity rows using only fields backed by the
Last.fm response (name, listener count, mbid, image) — no genre/category
guessing at discovery time; category is left as "Music" and enriched by
the existing entity_metrics worker on its next cycle like any other
entity.

IMPORTANT: Entity.primary_market has NO column default (see
app/models/entity.py) specifically because a default of "India" used to
silently overwrite explicit None values at insert time — every insert
here passes a real, explicit string ("India" or "Global"), never None.

Newly created entities are picked up automatically by the existing
entity_metrics worker (queries Entity.status == "active") and by
notification_signals.py — no other wiring needed.

Schedule: every 6 hours (same cadence as entity_metrics, so a newly
discovered artist gets its first real score within one cycle of the next).
"""

import asyncio

import structlog
from celery import Task
from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.workers.run_utils import run_async
from app.core.database import AsyncSessionLocal
from app.models.entity import Entity, EntityType, EntityStatus
from app.services.ingestion.lastfm_client import LastFMClient

logger = structlog.get_logger()

CHART_LIMIT = 100
MIN_LISTENERS_TO_CONSIDER = 5000  # filters out extreme long-tail noise
SIMILAR_ARTISTS_PER_SEED = 10     # how many similar-artist candidates to pull per India seed
SIMILAR_ARTIST_SEED_CAP = 15      # how many existing India entities to expand from per run (rate-limit friendly)
MIN_SIMILARITY_MATCH = 0.35       # Last.fm's own 0-1 "match" score


async def _load_existing_names(db) -> list[str]:
    result = await db.execute(select(Entity.name))
    return [n.lower() for (n,) in result.all() if n]


async def _load_india_seed_names(db) -> list[str]:
    """Existing entities already known to be India-relevant, used as seeds
    for similar-artist expansion."""
    result = await db.execute(
        select(Entity.name).where(Entity.primary_market == "India").limit(SIMILAR_ARTIST_SEED_CAP)
    )
    return [n for (n,) in result.all() if n]


def _is_already_tracked(candidate_name: str, existing_lower: list[str]) -> bool:
    cand = candidate_name.lower()
    for existing in existing_lower:
        if cand == existing or cand in existing or existing in cand:
            return True
    return False


async def _create_entity(db, name: str, market: str, mbid: str | None, image_url: str | None) -> bool:
    try:
        async with db.begin_nested():
            db.add(Entity(
                name=name,
                entity_type=EntityType.ARTIST.value,
                category="Music",  # unknown genre at discovery time — not guessed
                status=EntityStatus.ACTIVE.value,
                is_verified=False,
                is_international=(market == "Global"),
                is_active_on_district=False,
                primary_market=market,  # always an explicit real value — see module docstring
                data_sources=["lastfm_discovery"],
                external_ids={"lastfm_mbid": mbid} if mbid else {},
                image_url=image_url,
            ))
            await db.flush()
        return True
    except Exception as exc:
        logger.warning("artist_discovery: failed to create entity", name=name, market=market, error=str(exc))
        return False


async def _discover_from_chart(db, chart: list[dict], existing_lower: list[str], market: str) -> tuple[int, list[str]]:
    created = 0
    new_names: list[str] = []
    for entry in chart:
        name = entry.get("name")
        listeners = entry.get("listeners", 0)
        if not name or listeners < MIN_LISTENERS_TO_CONSIDER:
            continue
        if _is_already_tracked(name, existing_lower):
            continue
        if await _create_entity(db, name, market, entry.get("mbid"), entry.get("image_url")):
            created += 1
            new_names.append(name)
            existing_lower.append(name.lower())
    return created, new_names


async def _discover_india_similar(db, existing_lower: list[str], seed_names: list[str]) -> tuple[int, list[str]]:
    """
    Similar-artist expansion for India-relevant coverage beyond the India
    chart — surfaces names related to artists District already tracks that
    wouldn't show up on a national top-100 chart (e.g. a rising Punjabi-pop
    or indie-India act similar to an already-tracked artist).
    """
    created = 0
    new_names: list[str] = []

    async with LastFMClient() as client:
        for seed_name in seed_names:
            try:
                similar = await client.get_similar_artists(seed_name, limit=SIMILAR_ARTISTS_PER_SEED)
            except Exception as exc:
                logger.warning("artist_discovery: similar-artist fetch failed", seed=seed_name, error=str(exc))
                continue

            for entry in similar:
                name = entry.get("name")
                match_score = entry.get("match_score", 0)
                # Last.fm's artist.getsimilar endpoint never returns a
                # listeners figure at all (confirmed against the raw API
                # response — only match/mbid/url/image are present), unlike
                # the chart endpoints. Filtering on listeners here would
                # silently reject every real candidate; match_score is the
                # only real signal this endpoint provides.
                if not name or match_score < MIN_SIMILARITY_MATCH:
                    continue
                if _is_already_tracked(name, existing_lower):
                    continue

                # The similarity graph occasionally links a musician to a
                # non-musical channel (comedians, commentary/news channels
                # that happen to co-occur in listening data). Real artists
                # always carry Last.fm genre tags; verified empirically that
                # non-music entries (e.g. YouTube comedy channels) return an
                # empty tag list — a data-driven filter, not a name denylist.
                try:
                    tags = await client.get_artist_tags(name)
                except Exception:
                    tags = []
                if not tags:
                    logger.info("artist_discovery: skipped untagged (likely non-music) candidate", name=name)
                    continue

                if await _create_entity(db, name, "India", entry.get("mbid"), entry.get("image_url")):
                    created += 1
                    new_names.append(name)
                    existing_lower.append(name.lower())

    return created, new_names


async def _discover() -> dict:
    async with LastFMClient() as client:
        global_chart, india_chart = await asyncio.gather(
            client.get_top_artists_global(limit=CHART_LIMIT),
            client.get_top_artists_by_country("India", limit=CHART_LIMIT),
            return_exceptions=True,
        )

    if isinstance(global_chart, Exception):
        logger.warning("artist_discovery: global chart fetch failed", error=str(global_chart))
        global_chart = []
    if isinstance(india_chart, Exception):
        logger.warning("artist_discovery: india chart fetch failed", error=str(india_chart))
        india_chart = []

    async with AsyncSessionLocal() as db:
        existing_lower = await _load_existing_names(db)
        india_seed_names = await _load_india_seed_names(db)

        global_created, global_names = await _discover_from_chart(db, global_chart, existing_lower, "Global")
        india_chart_created, india_chart_names = await _discover_from_chart(db, india_chart, existing_lower, "India")
        india_similar_created, india_similar_names = await _discover_india_similar(db, existing_lower, india_seed_names)

        await db.commit()

    india_created = india_chart_created + india_similar_created
    india_names = india_chart_names + india_similar_names

    return {
        "global_chart_scanned": len(global_chart),
        "india_chart_scanned": len(india_chart),
        "india_similar_seeds_used": len(india_seed_names),
        "discovered_global": global_created,
        "discovered_india_chart": india_chart_created,
        "discovered_india_similar": india_similar_created,
        "discovered_india_total": india_created,
        "total_discovered": global_created + india_created,
        "new_names_global": global_names,
        "new_names_india": india_names,
    }


@celery_app.task(
    name="app.workers.artist_discovery.discover_new_artists",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def discover_new_artists(self: Task):
    """Entry point: scan Last.fm charts + similar-artist graph for artists not yet tracked. Runs every 6h."""
    logger.info("artist_discovery: starting discovery cycle")
    try:
        result = run_async(_discover())
        summary = {k: v for k, v in result.items() if not k.startswith("new_names")}
        logger.info("artist_discovery: discovery complete", **summary)
        if result["total_discovered"] > 0:
            logger.info(
                "artist_discovery: new artists found",
                global_names=result["new_names_global"],
                india_names=result["new_names_india"],
            )
        return result
    except Exception as exc:
        logger.error("artist_discovery: discovery failed", error=str(exc))
        raise self.retry(exc=exc)

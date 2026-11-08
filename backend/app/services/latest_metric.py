"""Helper: the most recent *scored* EntityMetric row per entity.

entity_metrics is an append-only time series written by two independent
workers: the metrics worker (always sets composite_score) and the social
listening worker (sentiment fields only, composite_score NULL). Taking the
newest row blindly therefore lets a social-only row shadow the entity's real
score, making it vanish from every ranking (8 of 294 entities were affected).

`latest_metric()` returns an aliased EntityMetric restricted to rows that were
scored (composite_score set, or v3-evaluated with score_version set - a NULL
composite there means "unrated: not enough verified data", never 0) and de-duplicated to one row per entity (Postgres
DISTINCT ON, newest first). Join to it like a normal table; use an OUTER join
when entities without a score must still be listed. Every page that shows a
score or ranking must go through this so the same KPI is identical everywhere.
"""
from sqlalchemy import or_, select
from sqlalchemy.orm import aliased

from app.models.entity import Entity
from app.models.metrics import EntityMetric


def latest_metric(scored_only: bool = True):
    q = select(EntityMetric)
    if scored_only:
        # v3 rows (score_version set) count even when composite is NULL = 'unrated'; legacy rows need a composite
        q = q.where(or_(EntityMetric.composite_score.isnot(None), EntityMetric.score_version.isnot(None)))
    sub = (
        q.distinct(EntityMetric.entity_id)
        .order_by(EntityMetric.entity_id, EntityMetric.time.desc())
        .subquery("latest_metric")
    )
    return aliased(EntityMetric, sub)


def trend_direction(velocity) -> str:
    """Single definition of rising/falling/stable used by every route."""
    v = velocity or 0
    return "rising" if v > 2 else ("falling" if v < -2 else "stable")


UNRATED_VERDICT = "Not enough verified data"


def score_fields(score, confidence=None, signals_used=None) -> dict:
    """Backward-compatible score block shared by every list/detail payload.
    composite_score None means 'unrated' (fewer than 2 verified signals, or no verified YouTube/Wikipedia evidence)."""
    return {
        "composite_score": round(float(score), 1) if score is not None else None,
        "unrated": score is None,
        "score_confidence": round(float(confidence), 2) if confidence is not None and score is not None else None,
        "signals_used": list(signals_used) if signals_used is not None and score is not None else ([] if score is None else None),
        "score_verdict": UNRATED_VERDICT if score is None else None,
    }

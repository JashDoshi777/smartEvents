"""Shared portfolio KPIs so executive / dashboard / portfolio can never disagree.

Definitions (identical everywhere):
  total_entities  = entities in the market scope
  scored          = entities with a composite v3 score (latest scored snapshot); the rest are 'unrated' (NULL, not 0)
  avg_score       = mean of those latest scores (1 decimal)
  domestic        = market "india"  (Indian primary market, not international)
  international   = market "global" (everything else, incl. foreign acts touring India)
domestic + international == total_entities for market=all.
"""
from sqlalchemy import func, select

from app.models.entity import Entity
from app.services.latest_metric import latest_metric
from app.services.market_scope import market_clause

# Score bands for the portfolio "health" label (composite v2 scale, see
# app/services/scoring/composite.py: log-scaled, avg ~46, top acts 85+).
STRONG_MIN = 60.0
GOOD_MIN = 40.0


def health_label(score) -> str:
    if score is None:
        return "Needs data"
    if score >= STRONG_MIN:
        return "Strong"
    if score >= GOOD_MIN:
        return "Good"
    return "Weak"


def stats_stmt(market: str = "all"):
    lm = latest_metric()
    return (
        select(
            func.count(Entity.id),
            func.count(lm.composite_score),
            func.avg(lm.composite_score),
            func.count(Entity.id).filter(market_clause("india")),
            func.count(Entity.id).filter(market_clause("global")),
        )
        .select_from(Entity)
        .outerjoin(lm, lm.entity_id == Entity.id)
        .where(market_clause(market))
    )


def stats_dict(row) -> dict:
    total, scored, avg, domestic, intl = row
    return {
        "total": total or 0,
        "scored": scored or 0,
        "unrated": max((total or 0) - (scored or 0), 0),
        "avg_score": round(float(avg), 1) if avg is not None else None,
        "domestic": domestic or 0,
        "international": intl or 0,
        "coverage_pct": round((scored or 0) / total * 100, 1) if total else 0.0,
    }

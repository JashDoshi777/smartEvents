"""Anchor-normalised Google Trends (pure maths + term/topic eligibility; no network).

Google Trends scales every request so that the highest point among the requested terms is 100. A lone term at "100"
only means "its own interest peaked recently", so the raw value says nothing about popularity level. We therefore
always request the FIXED ANCHOR together with up to 4 entities and store

    google_trend_relative = mean(entity series) / mean(anchor series)        (same request, geo=IN, 'today 3-m')

which is comparable across batches because the anchor is identical in every request. Anchor: Arijit Singh,
Knowledge Graph topic /m/08hr72, a persistently very-searched Indian artist so most entities are < 1.
Resolution caveat: Google returns integers, so an entity far below the anchor reads 0 (relative 0.0 = "below ~1% of the anchor").
recent_delta_pct = (mean of last 7 points - mean of previous 21 points) / mean of previous 21 points, in the entity's
own series, NULL when the previous mean is < MIN_PRIOR_MEAN points (integer rounding noise).
"""
from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List, Optional, Sequence

ANCHOR_TOPIC = "/m/08hr72"
ANCHOR_LABEL = "Arijit Singh"
GEO = "IN"
TIMEFRAME = "today 3-m"
MIN_PRIOR_MEAN = 3.0


def anchor_ratio(entity: Sequence[float], anchor: Sequence[float]) -> Optional[float]:
    """mean(entity)/mean(anchor); None if either series is empty or the anchor is all zero."""
    if not entity or not anchor:
        return None
    am = mean(anchor)
    if am <= 0:
        return None
    return round(mean(entity) / am, 4)


def recent_delta_pct(series: Sequence[float], recent: int = 7, prior: int = 21) -> Optional[float]:
    if len(series) < recent + prior:
        return None
    r, p = series[-recent:], series[-(recent + prior):-recent]
    pm = mean(p)
    if pm < MIN_PRIOR_MEAN:
        return None
    return round(100.0 * (mean(r) - pm) / pm, 1)


def summarize(entity: Sequence[float], anchor: Sequence[float]) -> Dict[str, Any]:
    return {"relative": anchor_ratio(entity, anchor), "recent_delta_pct": recent_delta_pct(entity),
            "entity_mean": round(mean(entity), 3) if entity else None, "anchor_mean": round(mean(anchor), 3) if anchor else None}


def term_allowed(name: str, entity_type: Optional[str], wikipedia_title: Optional[str], p31: Sequence[str] = ()) -> bool:
    """A plain-text term is only safe when the name is not a generic word and has no Wikipedia disambiguator."""
    from app.services.news_filter import disambiguator_of, is_generic_name
    if is_generic_name(name) or "Q4167410" in (p31 or ()):
        return False
    if disambiguator_of(wikipedia_title):          # 'Jawan (film)': the bare name collides with other pages
        return False
    if entity_type == "movie":                      # film titles are almost always common words/phrases
        return False
    return True


def make_batches(items: List[Any], size: int = 4) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]

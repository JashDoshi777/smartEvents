"""LiveIQ composite score (v2) — pure, dependency-free, unit-tested.

The composite is a 0-100 "how big / how hot is this entity" number built from
the signals the metrics worker collects.

v1 (linear) problem: audience counts are extremely heavy-tailed. Normalising
Last.fm listeners linearly against a 10M cap meant a genuinely big Indian act
(AP Dhillon: 135k listeners, 283k YT subs) earned ~1 point from Last.fm and
~0.6 from YouTube, so the blended score was driven almost entirely by Google
Trends and landed under 30. Only global megastars could reach 50+.

v2:
  * Count signals (listeners, subscribers, news mentions) use a log10 scale
    between a "floor" (0 pts) and a saturation "cap" (100 pts), clamped to
    [0, 100]. Monotonic, bounded, and 10x more listeners is always worth the
    same number of points. Floors/caps: Last.fm 1k..20M, YouTube 1k..200M,
    news 0..300 articles/7d.
  * Google Trends is already 0-100 and used as-is (clamped).
  * Weights are RENORMALISED over the signals that are actually present, so a
    missing source never counts as zero. Weights: Last.fm 30 / YouTube 25 /
    Trends 25 / News 20.
  * `data_completeness` (0-1) = share of total weight that was available. It is
    returned alongside the score so UIs can flag low-confidence scores.
  * Invalid inputs (None, NaN, inf, non-numeric) are treated as "missing";
    negatives are clamped to 0.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Tuple

# key -> (weight, kind, floor, cap). Log signals score 0 at `floor` and 100 at `cap`.
SIGNALS = {
    "lastfm_listeners": (0.30, "log", 1_000, 20_000_000),
    "youtube_subscribers": (0.25, "log", 1_000, 200_000_000),
    "google_trend_score": (0.25, "pct", 0, 100),
    "news_mentions_7d": (0.20, "log", 0, 300),
}
TOTAL_WEIGHT = sum(v[0] for v in SIGNALS.values())


def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def normalise(kind: str, value: float, floor: float, cap: float) -> float:
    value = max(value, 0.0)
    if kind == "pct":
        return min(value, 100.0)
    lo, hi = math.log10(1.0 + floor), math.log10(1.0 + cap)
    return min(100.0, max(0.0, 100.0 * (math.log10(1.0 + value) - lo) / (hi - lo)))


def compute_composite(metrics: Mapping[str, Any]) -> Tuple[Optional[float], float]:
    """Return (score 0-100 rounded to 2dp or None if no signal, data_completeness 0-1)."""
    score = 0.0
    weight_sum = 0.0
    for key, (weight, kind, floor, cap) in SIGNALS.items():
        v = _num(metrics.get(key))
        if v is None:
            continue
        score += normalise(kind, v, floor, cap) * weight
        weight_sum += weight
    if weight_sum == 0:
        return None, 0.0
    return round(min(100.0, max(0.0, score / weight_sum)), 2), round(weight_sum / TOTAL_WEIGHT, 2)


def compute_composite_score(metrics: Mapping[str, Any]) -> Optional[float]:
    return compute_composite(metrics)[0]

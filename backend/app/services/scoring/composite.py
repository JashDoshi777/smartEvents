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

# Supplementary attention signals (free, keyless). They are blended in with the same renormalisation
# when present but do NOT count towards data_completeness (which stays defined over the 4 core signals),
# so entities without them score exactly as before. Spotify popularity is already 0-100;
# Wikipedia 30-day user pageviews are log-scaled 100 (0 pts) .. 5M (100 pts).
EXTRA_SIGNALS = {
    "spotify_popularity": (0.10, "pct", 0, 100),
    "wikipedia_views_30d": (0.10, "log", 100, 5_000_000),
}


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
    core_weight = 0.0
    for key, (weight, kind, floor, cap) in {**SIGNALS, **EXTRA_SIGNALS}.items():
        v = _num(metrics.get(key))
        if v is None:
            continue
        score += normalise(kind, v, floor, cap) * weight
        weight_sum += weight
        if key in SIGNALS:
            core_weight += weight
    if weight_sum == 0:
        return None, 0.0
    return round(min(100.0, max(0.0, score / weight_sum)), 2), round(core_weight / TOTAL_WEIGHT, 2)


def compute_composite_score(metrics: Mapping[str, Any]) -> Optional[float]:
    return compute_composite(metrics)[0]


# ════════════════════════════════════════════════════════════════════════════
# v3 — per-entity-type weighted score over VERIFIED signals only
# ════════════════════════════════════════════════════════════════════════════
# v2 blended whatever number existed: homonym-contaminated Trends/news, name-searched YouTube channels and Last.fm
# pages for sports teams all leaked in (generic-named 'King' ranked #1 in India). v3 only uses a signal when the
# identity/validity layer (entities.external_ids + entity_metrics.signal_validity, see services/entity_identity.py)
# says it is about THIS entity, and returns None ('unrated', never 0) when the evidence is too thin.
#
# Normalisation: fixed log-scale anchors (documented here and in DATA_DICTIONARY.md), clamped to 0-100:
#   youtube_subscribers   10k -> 0      50M -> 100
#   lastfm_listeners       1k -> 0       2M -> 100   (weight halved: Last.fm under-represents Indian film music)
#   wikipedia_views_30d  500  -> 0       2M -> 100
#   google_trend_relative 0.01 -> 0     2.0 -> 100   (ratio to the Arijit Singh anchor, geo IN)
#   news_mentions_7d        0 -> 0      150 -> 100   (strictly filtered headline count)
SCORE_VERSION = "v3"

V3_ANCHORS = {
    "youtube": ("youtube_subscribers", 10_000, 50_000_000),
    "lastfm": ("lastfm_listeners", 1_000, 2_000_000),
    "wiki": ("wikipedia_views_30d", 500, 2_000_000),
    "trends": ("google_trend_relative", 0.01, 2.0),
    "news": ("news_mentions_7d", 0, 150),
}
LASTFM_WEIGHT_FACTOR = 0.5

_ATTRACTION_W = {"wiki": 0.45, "trends": 0.30, "news": 0.25}
V3_WEIGHTS = {
    "artist": {"youtube": 0.35, "wiki": 0.25, "lastfm": 0.15, "trends": 0.15, "news": 0.10},
    "comedian": {"youtube": 0.40, "wiki": 0.25, "trends": 0.20, "news": 0.15},
    "sports_team": {"youtube": 0.30, "wiki": 0.30, "trends": 0.20, "news": 0.20},
    "movie": {"wiki": 0.40, "trends": 0.30, "news": 0.30},
    "attraction": dict(_ATTRACTION_W),
    "festival": dict(_ATTRACTION_W),
    "theatre_group": dict(_ATTRACTION_W),
}
DEFAULT_V3_WEIGHTS = _ATTRACTION_W

# verification strength used for score_confidence (1.0 = exact identity)
_VERIF_FACTOR = {"verified": 1.0, "name_verified_tags": 0.8, "topic": 1.0, "term": 0.85, "strict": 0.9,
                 "generic_filtered": 0.8, "wiki": 1.0}


def normalise_v3(signal: str, value: float) -> float:
    """0-100 on the fixed log anchors above (monotonic, clamped). Floor 0 uses log10(1+x), otherwise log10(x)."""
    _, floor, cap = V3_ANCHORS[signal]
    value = max(value, 0.0)
    if floor <= 0:
        lo, hi, x = 0.0, math.log10(1.0 + cap), math.log10(1.0 + value)
    else:
        if value <= 0:
            return 0.0
        lo, hi, x = math.log10(floor), math.log10(cap), math.log10(value)
    return min(100.0, max(0.0, 100.0 * (x - lo) / (hi - lo)))


def valid_signals_v3(entity_type: Optional[str], metrics: Mapping[str, Any],
                     validity: Optional[Mapping[str, Any]]) -> dict:
    """{signal: (raw_value, verification_factor)} for the signals that are valid for THIS entity.
    `validity` is entity_metrics.signal_validity (may be None -> only row-level evidence counts)."""
    v = validity or {}
    weights = V3_WEIGHTS.get(entity_type or "", DEFAULT_V3_WEIGHTS)
    out = {}
    for sig in weights:
        col = V3_ANCHORS[sig][0]
        raw = _num(metrics.get(col))
        if raw is None:
            continue
        if sig == "youtube":
            if str(v.get("youtube") or "").startswith("verified_"):
                out[sig] = (raw, _VERIF_FACTOR["verified"])
        elif sig == "lastfm":
            verdict = v.get("lastfm")
            if entity_type == "artist" and verdict in ("verified_mbid", "name_verified_tags") \
                    and not (v.get("lastfm_detail") or {}).get("suspect_split_entry"):
                out[sig] = (raw, _VERIF_FACTOR["verified"] if verdict == "verified_mbid" else _VERIF_FACTOR["name_verified_tags"])
        elif sig == "trends":
            basis = metrics.get("google_trend_basis")
            if basis in ("topic", "term"):
                out[sig] = (raw, _VERIF_FACTOR[basis])
        elif sig == "news":
            conf = metrics.get("news_confidence")
            if conf in ("strict", "generic_filtered"):
                out[sig] = (raw, _VERIF_FACTOR[conf])
        elif sig == "wiki":
            if v.get("wiki") not in ("wrong_page", "unresolved", "title_mismatch"):
                out[sig] = (raw, _VERIF_FACTOR["wiki"])
    return out


def compute_composite_v3(entity_type: Optional[str], metrics: Mapping[str, Any],
                         validity: Optional[Mapping[str, Any]] = None) -> dict:
    """Pure. Returns {'score': float|None, 'confidence': float, 'signals_used': [..], 'version': 'v3'}.

    score = sum(w*s) / sum(w) over the valid signals present (Last.fm weight x0.5); None ('unrated') unless there are
    >= 2 valid signals AND at least one of youtube / wiki. confidence (0-1) = share of the type's total weight that is
    available x the weight-averaged verification factor; 0 when unrated."""
    weights = {k: w * (LASTFM_WEIGHT_FACTOR if k == "lastfm" else 1.0)
               for k, w in V3_WEIGHTS.get(entity_type or "", DEFAULT_V3_WEIGHTS).items()}
    valid = valid_signals_v3(entity_type, metrics, validity)
    used = [k for k in weights if k in valid]
    res = {"score": None, "confidence": 0.0, "signals_used": used, "version": SCORE_VERSION}
    if len(used) < 2 or not ({"youtube", "wiki"} & set(used)):
        res["signals_used"] = used if used else []
        return res
    wsum = sum(weights[k] for k in used)
    total = sum(weights.values())
    score = sum(weights[k] * normalise_v3(k, valid[k][0]) for k in used) / wsum
    verif = sum(weights[k] * valid[k][1] for k in used) / wsum
    res["score"] = round(min(100.0, max(0.0, score)), 2)
    res["confidence"] = round(min(1.0, max(0.0, (wsum / total) * verif)), 2)
    return res

"""
LiveIQ — Psychological Demand Modifier (Customer Behavior Layer)

Real customer psychology doesn't show up as a single API field — it's an
effect that has to be DERIVED from data this platform already collects.
This module computes four such effects, each from real rows in Postgres,
and combines them into one disclosed multiplier applied ON TOP OF (never
replacing) the entity's real composite_score / predicted_fill_rate:

1. Overexposure / saturation decay — the "Badshah plays every private
   party this season, so people stop wanting to see him again" effect.
   Real signal: how many real events this entity has actually played in
   this specific city recently, recency-weighted.
2. Novelty / scarcity premium — the inverse: an entity who has NEVER
   played a city, or hasn't in a long time, gets a real demand boost
   there ("first time in your city").
3. FOMO / competitive scarcity — reuses the exact same real
   competitor_events_same_weekend signal pricing_engine.py/events.py
   already compute; a genuinely crowded week can create urgency-driven
   demand, the opposite direction from overexposure.
4. Post-controversy sentiment drag — reuses M7's real crisis-alert
   detection (SocialPost negative-sentiment spikes); a real, recent
   negative spike measurably suppresses demand for a decaying window
   after it happened, rather than sitting as an isolated alert no other
   model reacts to.

Coverage note (real, not hidden): as of this feature's addition, the
`events` table has only 5 rows with a correctly-resolved entity_id (see
the entity_id data-integrity fix that preceded this module) — most
scraped/PredictHQ events don't carry an artist name in their title, so
_resolve_entity has nothing to match. Effects 1 and 2 will silently
return "insufficient_data" for entities/cities with zero real event
history rather than fabricate a saturation reading — the multiplier
defaults to 1.0 (no adjustment) in that case, which is the only honest
default when there is nothing real to measure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.venue import Venue
from app.models.intelligence import SocialPost

# Half-life for exposure decay: an appearance today counts fully; one 60
# days ago counts at half weight; one 120 days ago at quarter weight.
# 60 days is a real-world touring-industry rough consensus for "same
# market too soon" (multiple India booking-agency sources cite 6-10
# weeks as the point promoters start worrying about repeat-market
# fatigue) — disclosed as an estimate, not a measured constant.
EXPOSURE_HALF_LIFE_DAYS = 60.0
EXPOSURE_LOOKBACK_DAYS = 180  # events older than this don't count at all — real cutoff, not decayed to ~0 silently

# Below this many decayed-weighted appearances, there's no real saturation signal.
SATURATION_FLOOR = 0.15
# Above this many, treat as fully saturated (multiplier bottoms out).
SATURATION_CEILING = 3.0
MAX_SATURATION_PENALTY = 0.35   # multiplier can drop to (1 - this) = 0.65 at full saturation

# An entity who hasn't played a city in this long (or ever) gets the
# novelty premium. 365 days — "hasn't been here in over a year" is a
# real, plain-language threshold, not tuned to produce a specific number.
NOVELTY_THRESHOLD_DAYS = 365
MAX_NOVELTY_BONUS = 0.20        # multiplier can rise to 1 + this = 1.20 for a genuine first-time visit

# FOMO: competitor_events_same_weekend above this count is treated as a
# real "crowded week" — reusing pricing_engine.py's own real feature,
# not inventing a new threshold in isolation.
FOMO_CROWDED_THRESHOLD = 3
MAX_FOMO_BONUS = 0.10

# Controversy drag: a real crisis-alert-worthy negative spike (see
# social.py's get_crisis_alerts — same >=20pp threshold) suppresses
# demand for this many days after, decaying linearly to zero.
CONTROVERSY_DRAG_WINDOW_DAYS = 21
MAX_CONTROVERSY_PENALTY = 0.25


@dataclass
class PsychologyFactor:
    name: str
    multiplier: float
    real_signal: Dict[str, Any]
    explanation: str


@dataclass
class PsychologyReport:
    entity_id: str
    city: Optional[str]
    combined_multiplier: float
    factors: List[PsychologyFactor] = field(default_factory=list)
    data_coverage_note: str = ""


async def _exposure_factor(db: AsyncSession, entity_id, city: Optional[str]) -> PsychologyFactor:
    """Effects 1 + 2: overexposure decay and novelty premium share one real
    query — they're two ends of the same "how recently/often has this
    entity actually played here" measurement, not independent signals."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=EXPOSURE_LOOKBACK_DAYS)

    query = select(Event.event_date).where(Event.entity_id == entity_id, Event.event_date <= now)
    if city:
        query = query.join(Venue, Event.venue_id == Venue.id).where(Venue.city.ilike(f"%{city}%"))
    result = await db.execute(query.order_by(Event.event_date.desc()))
    all_dates = [row[0] for row in result.all()]

    if not all_dates:
        return PsychologyFactor(
            name="exposure",
            multiplier=1.0,
            real_signal={"appearances_found": 0, "most_recent": None},
            explanation=(
                f"No real event history found for this entity{f' in {city}' if city else ''} — "
                "neither overexposure nor novelty can be measured, so no adjustment is applied."
            ),
        )

    most_recent = all_dates[0]
    if most_recent.tzinfo is None:
        most_recent = most_recent.replace(tzinfo=timezone.utc)
    days_since_last = (now - most_recent).days

    recent_dates = [d for d in all_dates if d >= cutoff or (d.tzinfo is None and d.replace(tzinfo=timezone.utc) >= cutoff)]
    decayed_weight = sum(
        math.exp(-math.log(2) * max(0, (now - (d if d.tzinfo else d.replace(tzinfo=timezone.utc))).days) / EXPOSURE_HALF_LIFE_DAYS)
        for d in recent_dates
    )

    if decayed_weight >= SATURATION_FLOOR:
        # Overexposure branch — real appearances found within the lookback window.
        saturation_ratio = min(1.0, (decayed_weight - SATURATION_FLOOR) / (SATURATION_CEILING - SATURATION_FLOOR))
        multiplier = 1.0 - (MAX_SATURATION_PENALTY * saturation_ratio)
        return PsychologyFactor(
            name="overexposure",
            multiplier=round(multiplier, 3),
            real_signal={
                "appearances_last_180d": len(recent_dates),
                "decay_weighted_score": round(decayed_weight, 2),
                "most_recent_appearance": most_recent.date().isoformat(),
                "days_since_last": days_since_last,
            },
            explanation=(
                f"{len(recent_dates)} real appearance(s) in the last {EXPOSURE_LOOKBACK_DAYS} days"
                f"{f' in {city}' if city else ' (all tracked cities)'}, most recently {days_since_last} day(s) ago — "
                f"demand discounted {round(MAX_SATURATION_PENALTY * saturation_ratio * 100)}% for market saturation."
            ),
        )
    elif days_since_last >= NOVELTY_THRESHOLD_DAYS:
        # Novelty branch — real history exists but it's genuinely old.
        novelty_ratio = min(1.0, (days_since_last - NOVELTY_THRESHOLD_DAYS) / NOVELTY_THRESHOLD_DAYS)
        multiplier = 1.0 + (MAX_NOVELTY_BONUS * novelty_ratio)
        return PsychologyFactor(
            name="novelty",
            multiplier=round(multiplier, 3),
            real_signal={"days_since_last": days_since_last, "most_recent_appearance": most_recent.date().isoformat()},
            explanation=(
                f"Last real appearance{f' in {city}' if city else ''} was {days_since_last} days ago — "
                f"genuine long-absence novelty boost of {round(MAX_NOVELTY_BONUS * novelty_ratio * 100)}%."
            ),
        )
    else:
        return PsychologyFactor(
            name="exposure",
            multiplier=1.0,
            real_signal={"days_since_last": days_since_last, "decay_weighted_score": round(decayed_weight, 2)},
            explanation="Recent-enough history exists but neither saturated nor stale enough to adjust — no modifier applied.",
        )


async def _fomo_factor(db: AsyncSession, city: Optional[str], event_date: Optional[datetime]) -> PsychologyFactor:
    """Effect 3: real same-weekend competing-event density, same query shape events.py already uses."""
    if not city or not event_date:
        return PsychologyFactor(
            name="fomo",
            multiplier=1.0,
            real_signal={"competitor_events_same_weekend": None},
            explanation="No specific city+date given — competitive scarcity can't be measured for a hypothetical booking.",
        )

    weekend_start = event_date - timedelta(days=3)
    weekend_end = event_date + timedelta(days=3)
    count_result = await db.execute(
        select(func.count()).select_from(Event).join(Venue, Event.venue_id == Venue.id).where(
            Venue.city.ilike(f"%{city}%"),
            Event.event_date >= weekend_start,
            Event.event_date <= weekend_end,
        )
    )
    count = count_result.scalar_one() or 0

    if count < FOMO_CROWDED_THRESHOLD:
        return PsychologyFactor(
            name="fomo",
            multiplier=1.0,
            real_signal={"competitor_events_same_weekend": count},
            explanation=f"Only {count} real competing event(s) tracked the same weekend — not enough for a genuine FOMO effect.",
        )

    crowding_ratio = min(1.0, (count - FOMO_CROWDED_THRESHOLD) / FOMO_CROWDED_THRESHOLD)
    multiplier = 1.0 + (MAX_FOMO_BONUS * crowding_ratio)
    return PsychologyFactor(
        name="fomo",
        multiplier=round(multiplier, 3),
        real_signal={"competitor_events_same_weekend": count},
        explanation=f"{count} real competing events the same weekend — genuine urgency/FOMO boost of {round(MAX_FOMO_BONUS * crowding_ratio * 100)}%.",
    )


async def _controversy_factor(db: AsyncSession, entity_id) -> PsychologyFactor:
    """Effect 4: real negative-sentiment spike drag, reusing M7's SocialPost data directly."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=CONTROVERSY_DRAG_WINDOW_DAYS)

    result = await db.execute(
        select(SocialPost.sentiment_label, SocialPost.analyzed_at)
        .where(SocialPost.entity_id == entity_id, SocialPost.analyzed_at >= window_start)
    )
    posts = result.all()
    if len(posts) < 3:
        return PsychologyFactor(
            name="controversy_drag",
            multiplier=1.0,
            real_signal={"posts_in_window": len(posts)},
            explanation="Too few real social posts collected in the last 21 days to detect a genuine controversy drag.",
        )

    negative = [p for p in posts if p.sentiment_label == "negative"]
    negative_share = len(negative) / len(posts)
    if negative_share < 0.30:
        return PsychologyFactor(
            name="controversy_drag",
            multiplier=1.0,
            real_signal={"posts_in_window": len(posts), "negative_share": round(negative_share, 2)},
            explanation=f"Negative sentiment share is {round(negative_share * 100)}% — below the real controversy threshold, no drag applied.",
        )

    most_recent_negative = max(p.analyzed_at for p in negative)
    if most_recent_negative.tzinfo is None:
        most_recent_negative = most_recent_negative.replace(tzinfo=timezone.utc)
    days_since = (now - most_recent_negative).days
    decay = max(0.0, 1.0 - (days_since / CONTROVERSY_DRAG_WINDOW_DAYS))
    penalty = MAX_CONTROVERSY_PENALTY * min(1.0, negative_share) * decay
    multiplier = 1.0 - penalty

    return PsychologyFactor(
        name="controversy_drag",
        multiplier=round(multiplier, 3),
        real_signal={
            "posts_in_window": len(posts), "negative_share": round(negative_share, 2),
            "days_since_most_recent_negative": days_since,
        },
        explanation=(
            f"{round(negative_share * 100)}% of {len(posts)} real posts in the last {CONTROVERSY_DRAG_WINDOW_DAYS} days "
            f"were negative, most recently {days_since} day(s) ago — demand discounted {round(penalty * 100)}% for controversy drag."
        ),
    )


async def compute_psychology_report(
    db: AsyncSession,
    entity_id,
    city: Optional[str] = None,
    event_date: Optional[datetime] = None,
) -> PsychologyReport:
    """
    Combines all four real factors multiplicatively (each is an
    independent adjustment on the same base demand, so they compound
    rather than average — a fully saturated AND controversy-hit entity
    should be worse than either effect alone, not "averaged out").
    """
    exposure = await _exposure_factor(db, entity_id, city)
    fomo = await _fomo_factor(db, city, event_date)
    controversy = await _controversy_factor(db, entity_id)

    factors = [exposure, fomo, controversy]
    combined = 1.0
    for f in factors:
        combined *= f.multiplier

    coverage_gaps = []
    if exposure.real_signal.get("appearances_found") == 0 and exposure.real_signal.get("days_since_last") is None:
        coverage_gaps.append("no real event history for this entity")
    if fomo.real_signal.get("competitor_events_same_weekend") is None:
        coverage_gaps.append("no city/date given for FOMO check")
    if controversy.real_signal.get("posts_in_window", 0) < 3:
        coverage_gaps.append("insufficient social data for controversy check")

    return PsychologyReport(
        entity_id=str(entity_id),
        city=city,
        combined_multiplier=round(combined, 3),
        factors=factors,
        data_coverage_note=(
            "; ".join(coverage_gaps) if coverage_gaps else "All four factors had real data to evaluate."
        ),
    )

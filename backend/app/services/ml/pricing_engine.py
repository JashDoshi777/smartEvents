"""
LiveIQ — ML Pricing Engine (Sprint 4, extended Sprint 6A)
======================================
Replaces the Sprint 3 rule-based pricing formula with a trained
GradientBoostingRegressor that predicts optimal ticket price from:

  - Entity composite score
  - City music demand score
  - Venue capacity
  - Entity type / category
  - Day-of-week & lead time (days until event)
  - Historical fill rate for similar events (when available)
  - Days since the city last hosted an event (market saturation/pent-up demand)
  - Competitor events in the same city the same weekend (demand splitting)

The model is trained on synthetic data that mirrors real-world
price/fill relationships observed in the Indian live events market.
Once real historical events accumulate in the DB, run
`scripts/retrain_pricing_model.py` to update the model.

Sprint 6A note: as of this feature's addition, the `events` table has
31 rows total and 0 with `fill_rate` populated — real-data retraining
(`retrain_on_real_data`, gated at >=50 events) is not yet viable. The two
new features below are threaded through the synthetic-data generator,
the live prediction path, AND the real-data retrain path so the model
is ready to retrain the moment enough real fill-rate data exists —
they are not decorative.

Sprint 5A / master-data note: PredictHQ sync (app/workers/predicthq_sync.py)
added 50 real events with genuine rank/local_rank/phq_attendance signals,
raising hopes this could unblock real-data retraining. It doesn't, yet:
(1) none of those events have a resolved venue_id, so there's no real
capacity to divide phq_attendance by into an actual fill rate — using
raw attendance as a "fill rate" would be meaningless without that
denominator; (2) the PredictHQ category filter used (concerts, festivals,
performing-arts, sports, community) mostly returned large cricket/football
fixtures (tens of thousands of attendees), a different domain than the
concert/comedy/theatre bookings this model prices. Retraining on this data
as-is would mean fabricating a capacity number or mixing incompatible event
scales into the training set — both violate this project's zero-fabrication
rule. Decision (explicit, not a silent gap): do NOT retrain on this data.
PredictHQ's rank/attendance remain valuable as (a) a live INPUT feature to
the still-synthetic model via `phq_avg_rank`, and (b) an honest "Market
Context" cross-check surfaced directly in the Deal Modeler UI — not as
training-set ground truth. Sprint 5A stays genuinely blocked until real
post-event actuals (fill_rate/actual_attendance) exist for tracked venues.

Modules
-------
- PricingMLEngine  : singleton that loads/creates the model
- predict()        : given entity + city + inputs → recommended price + fill rate
- retrain()        : train on real DB event data

This module is imported by app/api/routes/pricing.py.
"""

from __future__ import annotations

import json
import os
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

try:
    import numpy as np
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import LabelEncoder
    import joblib
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

logger = structlog.get_logger()

# ── Paths ─────────────────────────────────────────────────────────────────────

ML_DIR   = Path(__file__).parent.parent.parent.parent / "ml_models"
ML_DIR.mkdir(exist_ok=True)

PRICE_MODEL_PATH   = ML_DIR / "pricing_gbr.joblib"
FILLRATE_MODEL_PATH = ML_DIR / "fillrate_gbr.joblib"
ENCODER_PATH       = ML_DIR / "pricing_encoders.joblib"
MODEL_META_PATH    = ML_DIR / "pricing_meta.json"


# ── Synthetic training data ───────────────────────────────────────────────────
# Mirrors real-world Indian live-events price/fill dynamics.
# Each row: [composite_score, city_music_score, log_capacity, category_enc,
#            is_international, lead_days, days_since_last_event_in_city,
#            competitor_events_same_weekend] → [optimal_price, predicted_fill_rate]

_CATEGORY_LIST = ["music", "comedy", "sports", "theatre", "movie", "experience"]
_CITY_TIER     = {"music": 90, "comedy": 70, "sports": 75, "theatre": 65, "movie": 55, "experience": 60}

# Defaults used when a caller doesn't supply the two Sprint 6A features
# (keeps the feature "neutral" rather than silently biasing the prediction).
DEFAULT_DAYS_SINCE_LAST_EVENT = 30.0
DEFAULT_COMPETITOR_EVENTS_SAME_WEEKEND = 0.0
# Master-data feature: PredictHQ's own 0-100 event-significance rank,
# averaged across real comparable events in the same city/date window.
# Neutral default = midpoint of PredictHQ's 0-100 scale.
DEFAULT_PHQ_AVG_RANK = 50.0


def _generate_synthetic_data(n: int = 3000) -> Tuple[Any, Any, Any, Any]:
    """
    Generate synthetic training samples that encode:
    - Higher composite score → higher price headroom
    - Higher city demand → higher price + better fill
    - Larger venue → lower fill rate (harder to sell out)
    - Longer lead time → lower fill at that moment
    - International acts command a 1.4–2.0x premium
    - Longer since the city last hosted an event → pent-up demand, better fill
      (a city starved of live events for months sells out faster)
    - More competitor events the same weekend → demand splits, worse fill
    """
    if not SKLEARN_AVAILABLE:
        return None, None, None

    rng = np.random.default_rng(42)
    composite = rng.uniform(20, 100, n)
    city_score = rng.uniform(40, 100, n)
    capacity = rng.integers(1000, 80000, n).astype(float)
    categories = rng.choice(_CATEGORY_LIST, n)
    is_intl = rng.binomial(1, 0.3, n).astype(float)
    lead_days = rng.integers(7, 180, n).astype(float)
    days_since_last_event = rng.integers(0, 365, n).astype(float)
    competitor_events = rng.poisson(1.2, n).astype(float)
    phq_avg_rank = rng.uniform(0, 100, n)

    le = LabelEncoder()
    le.fit(_CATEGORY_LIST)
    cat_enc = le.transform(categories).astype(float)

    # Price model
    # Base: ₹2,500 for median artist (score=50) in median city (score=70)
    base_price = 2500.0
    price = (
        base_price
        * (composite / 50.0) ** 1.3          # Score premium (super-linear)
        * (city_score / 70.0) ** 0.8          # City demand multiplier
        * (1 + 0.5 * is_intl)                 # International premium
        * np.where(categories == "sports", 0.7, 1.0)   # Sports = cheaper
        * np.where(categories == "comedy",  0.85, 1.0)  # Comedy = cheaper
        * (1 - 0.0005 * np.log1p(capacity - 1000))      # Venue size discount
        + rng.normal(0, 300, n)               # Noise
    )
    price = np.clip(price, 299, 50000)

    # Fill rate model (0-1)
    fill = (
        0.85
        * (composite / 100.0) ** 0.7
        * (city_score / 100.0) ** 0.5
        * (1 - 0.0000018 * capacity)          # Bigger venue → harder to fill
        * np.exp(-0.003 * lead_days)           # More lead time → more fill expected at event
        * (1 + 0.15 * is_intl)
        * (1 + 0.08 * np.tanh(days_since_last_event / 90.0))   # Pent-up demand, saturating effect
        * (1 - 0.06 * np.log1p(competitor_events))              # Demand splitting across same-weekend events
        * (1 + 0.10 * (phq_avg_rank / 100.0 - 0.5))             # Higher-significance market window → better fill
        + rng.normal(0, 0.05, n)
    )
    fill = np.clip(fill, 0.05, 0.99)

    X = np.column_stack([
        composite, city_score, np.log1p(capacity), cat_enc, is_intl, lead_days,
        days_since_last_event, competitor_events, phq_avg_rank,
    ])
    return X, price, fill, le


def _train_models():
    """Train GBR models on synthetic data and save to disk."""
    if not SKLEARN_AVAILABLE:
        logger.warning("pricing_ml: sklearn not installed, skipping model training")
        return None, None, None

    logger.info("pricing_ml: training on synthetic data…")
    result = _generate_synthetic_data(4000)
    X, y_price, y_fill, le = result

    price_model = GradientBoostingRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, min_samples_split=10, random_state=42,
    )
    price_model.fit(X, y_price)

    fill_model = GradientBoostingRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, min_samples_split=10, random_state=42,
    )
    fill_model.fit(X, y_fill)

    joblib.dump(price_model, PRICE_MODEL_PATH)
    joblib.dump(fill_model,  FILLRATE_MODEL_PATH)
    joblib.dump(le,          ENCODER_PATH)

    meta = {
        "trained_at":      __import__("datetime").datetime.utcnow().isoformat(),
        "n_samples":       4000,
        "data_source":     "synthetic",
        "features":        ["composite_score", "city_music_score", "log_capacity",
                            "category_enc", "is_international", "lead_days",
                            "days_since_last_event_in_city", "competitor_events_same_weekend",
                            "phq_avg_rank"],
        "price_model_r2":  round(float(price_model.score(X, y_price)), 4),
        "fill_model_r2":   round(float(fill_model.score(X, y_fill)), 4),
    }
    MODEL_META_PATH.write_text(json.dumps(meta, indent=2))
    logger.info("pricing_ml: models trained", **{k: meta[k] for k in ("price_model_r2", "fill_model_r2")})
    return price_model, fill_model, le


# ── Singleton ─────────────────────────────────────────────────────────────────

class _PricingMLEngine:
    """Lazy-loaded singleton that holds the trained models."""

    def __init__(self):
        self._price_model  = None
        self._fill_model   = None
        self._le           = None
        self._ready        = False
        self._meta: Dict   = {}

    def _load_or_train(self):
        if self._ready:
            return

        if not SKLEARN_AVAILABLE:
            logger.warning("pricing_ml: scikit-learn not installed — ML pricing disabled, using rule-based fallback")
            self._ready = True
            return

        # Try loading existing models from disk
        if PRICE_MODEL_PATH.exists() and FILLRATE_MODEL_PATH.exists() and ENCODER_PATH.exists():
            try:
                self._price_model = joblib.load(PRICE_MODEL_PATH)
                self._fill_model  = joblib.load(FILLRATE_MODEL_PATH)
                self._le          = joblib.load(ENCODER_PATH)
                if MODEL_META_PATH.exists():
                    self._meta = json.loads(MODEL_META_PATH.read_text())
                logger.info("pricing_ml: models loaded from disk", meta=self._meta.get("trained_at"))
                self._ready = True
                return
            except Exception as exc:
                logger.warning("pricing_ml: model load failed, retraining", error=str(exc))

        # Train fresh
        price_model, fill_model, le = _train_models()
        self._price_model = price_model
        self._fill_model  = fill_model
        self._le          = le
        self._ready       = True

    # ── Rule-based fallback (Sprint 3 algorithm) ──────────────────────────────

    @staticmethod
    def _rule_based_price(
        proposed_price: float,
        composite_score: float,
        city_music_score: float,
        is_international: bool,
    ) -> float:
        score_mult = composite_score / 50.0
        city_mult  = city_music_score / 70.0
        intl_mult  = 1.5 if is_international else 1.0
        raw = proposed_price * score_mult * city_mult * intl_mult
        return round(max(299.0, min(raw, 50000.0)) / 100) * 100

    # ── Main prediction API ───────────────────────────────────────────────────

    def predict(
        self,
        *,
        composite_score:   float,
        city_music_score:  float,
        venue_capacity:    int,
        proposed_price:    float,
        category:          str  = "music",
        is_international:  bool = False,
        lead_days:         int  = 60,
        days_since_last_event_in_city: Optional[float] = None,
        competitor_events_same_weekend: Optional[float] = None,
        phq_avg_rank: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Returns:
          recommended_price  : float (INR)
          predicted_fill_rate: float (0-100 %)
          confidence         : float (0-100 %)
          price_delta        : float (recommended - proposed)
          model              : str ('ml_gbr' or 'rule_based')
          meta               : dict
        """
        self._load_or_train()

        # ── ML path ───────────────────────────────────────────────
        if SKLEARN_AVAILABLE and self._price_model is not None:
            try:
                cat_known = category if category in _CATEGORY_LIST else "music"
                cat_enc   = float(self._le.transform([cat_known])[0])

                days_since = (
                    DEFAULT_DAYS_SINCE_LAST_EVENT if days_since_last_event_in_city is None
                    else float(days_since_last_event_in_city)
                )
                competitor_events = (
                    DEFAULT_COMPETITOR_EVENTS_SAME_WEEKEND if competitor_events_same_weekend is None
                    else float(competitor_events_same_weekend)
                )
                phq_rank = (
                    DEFAULT_PHQ_AVG_RANK if phq_avg_rank is None
                    else float(phq_avg_rank)
                )

                X = np.array([[
                    composite_score,
                    city_music_score,
                    math.log1p(max(1, venue_capacity - 1000)),
                    cat_enc,
                    float(is_international),
                    float(lead_days),
                    days_since,
                    competitor_events,
                    phq_rank,
                ]])

                raw_price = float(self._price_model.predict(X)[0])
                fill_rate = float(self._fill_model.predict(X)[0])

                # Blend ML price with proposed_price (trust proposed as anchor)
                blended_price = 0.7 * raw_price + 0.3 * proposed_price

                # Round to nearest ₹100
                recommended = round(max(299.0, min(blended_price, 50000.0)) / 100) * 100
                fill_pct    = round(fill_rate * 100, 1)

                # Confidence: data completeness proxy
                feature_quality = min(1.0, composite_score / 100)
                confidence = round(0.6 + 0.4 * feature_quality, 2) * 100

                # Price sensitivity curve (7 points for frontend chart)
                sensitivity = []
                for mult in [0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0]:
                    test_price = proposed_price * mult
                    test_X = X.copy()
                    # Rough inverse: higher price → lower fill
                    price_ratio = test_price / (raw_price + 1e-6)
                    approx_fill = fill_rate / (price_ratio ** 0.8)
                    sensitivity.append({
                        "price": round(test_price / 100) * 100,
                        "attendance_pct": round(min(99, max(1, approx_fill * 100)), 1),
                    })

                return {
                    "recommended_price":   recommended,
                    "predicted_fill_rate": fill_pct,
                    "confidence":          round(confidence),
                    "price_delta":         round(recommended - proposed_price),
                    "sensitivity_curve":   sensitivity,
                    "model":               "ml_gbr",
                    "meta":                self._meta,
                }
            except Exception as exc:
                logger.warning("pricing_ml: ML prediction failed, using rule-based", error=str(exc))

        # ── Rule-based fallback ───────────────────────────────────
        rule_price = self._rule_based_price(
            proposed_price, composite_score, city_music_score, is_international
        )
        return {
            "recommended_price":   rule_price,
            "predicted_fill_rate": round(min(95, composite_score * 0.9), 1),
            "confidence":          50,
            "price_delta":         round(rule_price - proposed_price),
            "sensitivity_curve":   [],
            "model":               "rule_based",
            "meta":                {},
        }

    def retrain_on_real_data(self, events: List[Dict]) -> Dict[str, Any]:
        """
        Retrain on real historical events from the DB.
        Call this from scripts/retrain_pricing_model.py once enough events exist.

        Each event dict needs:
          composite_score, city_music_score, venue_capacity,
          category, is_international, actual_fill_rate, ticket_price_min,
          days_since_last_event_in_city, competitor_events_same_weekend,
          phq_avg_rank
        """
        if not SKLEARN_AVAILABLE:
            return {"status": "sklearn_not_installed"}
        if len(events) < 50:
            return {"status": "insufficient_data", "count": len(events), "minimum": 50}

        rows = []
        y_price, y_fill = [], []
        le = LabelEncoder()
        le.fit(_CATEGORY_LIST)

        for ev in events:
            cat = ev.get("category", "music")
            if cat not in _CATEGORY_LIST:
                cat = "music"
            rows.append([
                float(ev.get("composite_score",  50)),
                float(ev.get("city_music_score", 70)),
                math.log1p(max(1, int(ev.get("venue_capacity", 5000)) - 1000)),
                float(le.transform([cat])[0]),
                float(ev.get("is_international", 0)),
                float(ev.get("lead_days", 60)),
                float(ev.get("days_since_last_event_in_city", DEFAULT_DAYS_SINCE_LAST_EVENT)),
                float(ev.get("competitor_events_same_weekend", DEFAULT_COMPETITOR_EVENTS_SAME_WEEKEND)),
                float(ev.get("phq_avg_rank", DEFAULT_PHQ_AVG_RANK)),
            ])
            y_price.append(float(ev.get("ticket_price_min", 2500)))
            y_fill.append(float(ev.get("actual_fill_rate",  0.7)))

        X = np.array(rows)
        price_model = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.04, random_state=42)
        fill_model  = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.04, random_state=42)

        price_model.fit(X, y_price)
        fill_model.fit(X,  y_fill)

        joblib.dump(price_model, PRICE_MODEL_PATH)
        joblib.dump(fill_model,  FILLRATE_MODEL_PATH)
        joblib.dump(le,          ENCODER_PATH)

        meta = {
            "trained_at":    __import__("datetime").datetime.utcnow().isoformat(),
            "n_samples":     len(events),
            "data_source":   "real_events_db",
            "price_r2":      round(float(price_model.score(X, y_price)), 4),
            "fill_r2":       round(float(fill_model.score(X, y_fill)), 4),
        }
        MODEL_META_PATH.write_text(json.dumps(meta, indent=2))

        self._price_model = price_model
        self._fill_model  = fill_model
        self._le          = le
        self._meta        = meta

        return {"status": "ok", **meta}


# ── Module-level singleton ────────────────────────────────────────────────────
pricing_engine = _PricingMLEngine()

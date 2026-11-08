"""
LiveIQ — Anomaly Detection Worker (Sprint 4 — ML)
===================================================
Uses sklearn IsolationForest to detect breakout anomalies in entity metric history.

What it does
------------
1. Loads the last N metric rows per entity from entity_metrics.
2. Fits an IsolationForest on [composite_score, google_trend_score,
   news_mentions_7d, trend_velocity] per entity.
3. Labels the latest data point as:
   - Breakout  (-1 from IsolationForest + composite score rising)
   - Anomaly   (-1 from IsolationForest + composite score falling)
   - Normal    (+1)
4. Writes breakout_probability back to the entity_metrics row.
5. Stores detected breakouts to MongoDB (raw alerts) so
   /dashboard/alerts can surface them without re-running ML each time.

Schedule: every 6 hours (after entity_metrics worker completes)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json

import structlog
from celery import Task

try:
    import numpy as np
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from app.workers.celery_app import celery_app
from app.workers.run_utils import run_async
from app.core.database import AsyncSessionLocal
from app.core.mongodb import get_mongo_db, mongo_available
from app.models.metrics import EntityMetric
from app.models.entity import Entity

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = structlog.get_logger()

# ── Config ────────────────────────────────────────────────────────────────────

# Minimum rows per entity to run IsolationForest (needs history)
MIN_ROWS_FOR_ML = 5
# IsolationForest contamination — expected fraction of outliers
CONTAMINATION = 0.1
# Feature columns used for anomaly detection
FEATURES = [
    "composite_score",
    "google_trend_score",
    "news_mentions_7d",
    "trend_velocity",
]

MONGO_COLLECTION = "breakout_alerts"


# ── Feature extraction ────────────────────────────────────────────────────────

def _extract_features(rows: List[EntityMetric]) -> Optional["np.ndarray"]:
    """
    Convert ORM rows → numpy feature matrix.
    Fills None values with column median.
    """
    if not SKLEARN_AVAILABLE:
        return None

    data = []
    for row in rows:
        data.append([
            getattr(row, "composite_score",    None),
            getattr(row, "google_trend_score", None),
            getattr(row, "news_mentions_7d",   None),
            getattr(row, "trend_velocity",     None),
        ])
    # Use None -> NaN directly so genuine zero values (e.g. 0 news mentions)
    # are NOT confused with missing data — only true NULLs get median-filled.
    arr = np.array(
        [[np.nan if v is None else float(v) for v in row] for row in data],
        dtype=np.float64,
    )

    col_medians = np.nanmedian(arr, axis=0)
    col_medians = np.nan_to_num(col_medians, nan=0.0)
    inds = np.where(np.isnan(arr))
    arr[inds] = np.take(col_medians, inds[1])

    return arr


# ── Per-entity anomaly detection ──────────────────────────────────────────────

def _detect_for_entity(rows: List[EntityMetric]) -> Dict[str, Any]:
    """
    Run IsolationForest on this entity's metric history.
    Returns:
      - is_breakout:        bool
      - is_anomaly:         bool
      - breakout_probability: float 0-1
      - anomaly_score:      float (raw IF score, more negative = more anomalous)
      - latest_composite:   float
      - delta:              float (composite change vs previous row)
    """
    if not SKLEARN_AVAILABLE or len(rows) < MIN_ROWS_FOR_ML:
        return {
            "is_breakout": False,
            "is_anomaly": False,
            "breakout_probability": 0.0,
            "anomaly_score": 0.0,
            "latest_composite": getattr(rows[-1], "composite_score", None) or 0.0 if rows else 0.0,
            "delta": 0.0,
            "reason": "insufficient_history",
        }

    X = _extract_features(rows)
    if X is None:
        return {"is_breakout": False, "is_anomaly": False, "breakout_probability": 0.0,
                "anomaly_score": 0.0, "latest_composite": 0.0, "delta": 0.0}

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    iso = IsolationForest(
        n_estimators=100,
        contamination=CONTAMINATION,
        random_state=42,
    )
    iso.fit(X_scaled)

    # Predict on the latest row only
    latest_X = X_scaled[-1:, :]
    pred = iso.predict(latest_X)[0]           # -1 = anomaly, +1 = normal
    score = iso.score_samples(latest_X)[0]    # More negative = more anomalous

    # Convert raw IF score → 0-1 probability (logistic-style)
    # score is typically in [-0.7, 0.2]; we flip and normalise
    breakout_prob = float(1.0 / (1.0 + np.exp(5 * (score + 0.3))))

    latest_composite = float(rows[-1].composite_score or 0)
    prev_composite   = float(rows[-2].composite_score or 0) if len(rows) >= 2 else latest_composite
    delta = latest_composite - prev_composite

    is_anomaly  = pred == -1
    is_breakout = is_anomaly and delta > 0  # Positive outlier = breakout

    return {
        "is_breakout":          is_breakout,
        "is_anomaly":           is_anomaly,
        "breakout_probability": round(breakout_prob, 4),
        "anomaly_score":        round(float(score), 4),
        "latest_composite":     round(latest_composite, 2),
        "delta":                round(delta, 2),
    }


# ── MongoDB alert persistence ─────────────────────────────────────────────────

async def _persist_alert(entity_name: str, entity_id: str, result: Dict[str, Any]):
    """Write a breakout alert to MongoDB for /dashboard/alerts to consume."""
    # Mongo is optional infrastructure and permanently absent in dev: skip
    # quietly (negative-cached, no 1.5s timeout per alert) instead of failing.
    # Postgres alternative: the same signals are persisted to the
    # `trend_signals` table by app/workers/notification_signals.py, which is
    # what /notifications and /dashboard/alerts actually read.
    if not await mongo_available():
        logger.info("anomaly_detector: Mongo unavailable - alert persistence skipped", entity=entity_name)
        return
    try:
        # get_mongo_db() is sync (returns AsyncIOMotorDatabase directly) —
        # awaiting it raised TypeError every call, silently swallowed by
        # this try/except, so alerts were never actually persisted to Mongo.
        db = get_mongo_db()
        if db is None:
            return

        coll = db[MONGO_COLLECTION]
        ts   = datetime.now(timezone.utc)

        alert = {
            "entity_id":    entity_id,
            "entity_name":  entity_name,
            "type":         "breakout" if result["is_breakout"] else "anomaly",
            "title":        f"{'Breakout' if result['is_breakout'] else 'Anomaly'}: {entity_name}",
            "message":      (
                f"Composite score rose by {result['delta']:+.1f} pts to {result['latest_composite']:.0f} "
                f"(IsolationForest anomaly score: {result['anomaly_score']:.3f})"
                if result["is_breakout"]
                else
                f"Unusual metric pattern detected. Score: {result['latest_composite']:.0f}, "
                f"delta: {result['delta']:+.1f}"
            ),
            "severity":     "high" if abs(result["delta"]) > 15 else "medium",
            "breakout_probability": result["breakout_probability"],
            "anomaly_score": result["anomaly_score"],
            "ts":           ts.isoformat(),
            "created_at":   ts,
        }

        # Upsert — replace existing alert for same entity within 12h window
        await coll.update_one(
            {
                "entity_id": entity_id,
                "created_at": {"$gte": datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)},
            },
            {"$set": alert},
            upsert=True,
        )
        logger.info("anomaly_detector: alert persisted", entity=entity_name, type=alert["type"])
    except Exception as exc:
        logger.warning("anomaly_detector: alert persistence failed", error=str(exc))


# ── Main async pipeline ───────────────────────────────────────────────────────

async def _run_detection() -> Dict[str, Any]:
    """
    1. Load all entities that have at least MIN_ROWS_FOR_ML metric rows.
    2. For each entity, load its last 30 metric rows (time-ordered).
    3. Run IsolationForest.
    4. Write breakout_probability back to the latest EntityMetric row.
    5. Persist breakout alerts to MongoDB.
    """
    if not SKLEARN_AVAILABLE:
        return {
            "status": "sklearn_not_installed",
            "message": "Install scikit-learn: pip install scikit-learn==1.5.2",
        }

    breakouts  = 0
    anomalies  = 0
    processed  = 0

    async with AsyncSessionLocal() as session:
        # Get all entity_ids that have metric history
        result = await session.execute(
            select(EntityMetric.entity_id, func.count(EntityMetric.entity_id).label("cnt"))
            .group_by(EntityMetric.entity_id)
            .having(func.count(EntityMetric.entity_id) >= 2)  # At least 2 rows
        )
        entity_counts = result.all()

        for entity_id, count in entity_counts:
            # Load entity name
            ent_result = await session.execute(
                select(Entity.name).where(Entity.id == entity_id).limit(1)
            )
            entity_name = ent_result.scalar_one_or_none() or str(entity_id)

            # Load metric history (up to 30 most recent rows)
            rows_result = await session.execute(
                select(EntityMetric)
                .where(EntityMetric.entity_id == entity_id)
                .order_by(EntityMetric.time.asc())
                .limit(30)
            )
            rows = rows_result.scalars().all()

            if not rows:
                continue

            detection = _detect_for_entity(list(rows))
            processed += 1

            # Write breakout_probability to the latest metric row
            latest_row = rows[-1]
            latest_row.breakout_probability = detection["breakout_probability"]
            session.add(latest_row)

            if detection["is_breakout"]:
                breakouts += 1
                await _persist_alert(entity_name, str(entity_id), detection)
                logger.info(
                    "anomaly_detector: BREAKOUT detected",
                    entity=entity_name,
                    prob=detection["breakout_probability"],
                    delta=detection["delta"],
                )
            elif detection["is_anomaly"]:
                anomalies += 1
                logger.info(
                    "anomaly_detector: anomaly detected",
                    entity=entity_name,
                    score=detection["anomaly_score"],
                )

        await session.commit()

    return {
        "status":     "ok",
        "processed":  processed,
        "breakouts":  breakouts,
        "anomalies":  anomalies,
        "ran_at":     datetime.now(timezone.utc).isoformat(),
        "ml_backend": "sklearn_IsolationForest",
    }


# ── Celery Task ───────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.workers.anomaly_detection.detect_breakouts",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def detect_breakouts(self: Task):
    """
    Entry point: run IsolationForest anomaly detection on all entity metrics.
    Writes breakout_probability back to entity_metrics and alerts to MongoDB.
    """
    logger.info("anomaly_detector: starting detection run")
    try:
        result = run_async(_run_detection())
        logger.info("anomaly_detector: run complete", **result)
        return result
    except Exception as exc:
        logger.error("anomaly_detector: run failed", error=str(exc))
        raise self.retry(exc=exc)

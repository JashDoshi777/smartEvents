"""Training of the fill-rate / pricing models from REAL District sales rows (never synthetic)."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.ml import pricing_engine as pe

MIN_REAL_ROWS = 150
FEATURES = ["composite_score", "city_music_score", "log_capacity", "category_enc", "is_international", "lead_days",
            "days_since_last_event_in_city", "competitor_events_same_weekend", "phq_avg_rank"]
SYNTHETIC_SOURCES = {"synthetic", "seed", "demo", "mock"}


class InsufficientData(Exception):
    pass


def eligible(ev: Dict[str, Any]) -> bool:
    """A REAL training row: actuals present and sane (tickets_sold, capacity > 0, fill <= 1.05), not a synthetic source."""
    try:
        cap, sold = ev.get("total_capacity"), ev.get("tickets_sold")
        if cap is None or sold is None or cap <= 0 or sold < 0 or sold / cap > 1.05:
            return False
    except TypeError:
        return False
    return str(ev.get("source") or "").lower() not in SYNTHETIC_SOURCES


def require_enough(rows: Sequence[Any], minimum: int = MIN_REAL_ROWS) -> None:
    if len(rows) < minimum:
        raise InsufficientData(
            f"Refusing to train: {len(rows)} real events with tickets_sold & capacity (need >= {minimum}). "
            "Import District sales with scripts/import_district_sales.py first. Synthetic data is never used.")


def data_hash(rows: Sequence[Sequence[float]], y: Sequence[float]) -> str:
    h = hashlib.sha256()
    for r, t in sorted(zip((tuple(round(v, 6) for v in r) for r in rows), (round(v, 6) for v in y))):
        h.update(repr((r, t)).encode())
    return h.hexdigest()[:16]


def next_version(root: Path) -> str:
    nums = [int(p.name[1:]) for p in root.glob("v*") if p.name[1:].isdigit()]
    return f"v{(max(nums) + 1) if nums else 1}"


def cross_validate(X, y, folds: int = 5) -> Dict[str, float]:
    import numpy as np
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import KFold, cross_val_predict
    est = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, min_samples_leaf=3, random_state=42)
    pred = cross_val_predict(est, np.array(X), np.array(y), cv=KFold(min(folds, len(y)), shuffle=True, random_state=42))
    return {"mae": round(float(mean_absolute_error(y, pred)), 4), "r2": round(float(r2_score(y, pred)), 4)}


def train_and_save(X: List[List[float]], y_fill: List[float], y_price: List[Optional[float]], root: Path,
                   notes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    import joblib
    import numpy as np
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import LabelEncoder
    require_enough(X)
    root.mkdir(parents=True, exist_ok=True)
    version = next_version(root)
    out = root / version
    out.mkdir()
    Xa = np.array(X)
    mk = lambda: GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, min_samples_leaf=3, random_state=42)
    fill_m = mk().fit(Xa, np.array(y_fill))
    pidx = [i for i, p in enumerate(y_price) if p]
    metrics = {"fill_rate": cross_validate(X, y_fill)}
    if len(pidx) >= MIN_REAL_ROWS:
        price_m = mk().fit(Xa[pidx], np.array([y_price[i] for i in pidx]))
        metrics["price"] = cross_validate([X[i] for i in pidx], [y_price[i] for i in pidx])
    else:
        # honest: no price model of our own; reuse the baseline price model/encoders but record it
        price_m = joblib.load(pe.PRICE_MODEL_PATH)
        metrics["price"] = None
    le = LabelEncoder().fit(pe._CATEGORY_LIST)
    joblib.dump(price_m, out / "pricing_gbr.joblib")
    joblib.dump(fill_m, out / "fillrate_gbr.joblib")
    joblib.dump(le, out / "pricing_encoders.joblib")
    meta = {
        "version": version, "trained_at": datetime.now(timezone.utc).isoformat(), "training_rows": len(X),
        "price_rows": len(pidx), "price_model": "district-trained" if metrics["price"] else "baseline-reused",
        "cv_folds": 5, "metrics": metrics, "data_hash": data_hash(X, y_fill), "features": FEATURES,
        "data_source": "district_sales_real_events", **(notes or {}),
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2))
    return meta


def promote(root: Path, version: str, ml_dir: Path) -> None:
    d = root / version
    if not (d / "metadata.json").exists():
        raise FileNotFoundError(f"{d} has no trained artifacts")
    (ml_dir / "promoted.json").write_text(json.dumps({"version": version, "path": str(d.relative_to(ml_dir))}))

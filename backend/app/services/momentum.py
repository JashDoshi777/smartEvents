"""Momentum metrics computed from real weekly Wikipedia attention history (entity_attention_weekly).

Definitions (weeks are complete ISO weeks; `last` = the most recent complete week in the data):
  views_7d              = total views in `last`
  views_28d_avg_weekly  = mean of the 4 weeks before `last` (needs >= MIN_BASELINE_WEEKS of them present)
  momentum_pct          = 100 * (views_7d - baseline) / baseline, NULL when baseline < MIN_BASELINE (1,000 views/week)
  label                 = 'rising' if momentum_pct >= RISING_PCT, 'falling' if <= FALLING_PCT AND |robust_z| >= MIN_ABS_Z
                          (z computed against the entity's own history; unknown z -> 'steady'), else 'steady'; NULL if momentum NULL
  robust_z              = 0.6745 * (views_7d - median(history)) / max(MAD, 5% of median, 1), history = the weeks before
                          `last` (needs >= MIN_HISTORY_WEEKS), NULL otherwise
A tiny baseline makes percentages meaningless (3 -> 9 views is +200%), hence MIN_BASELINE.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, median
from typing import Any, Dict, List, Mapping, Optional

MIN_BASELINE = 1000.0        # views/week (mean of prior 4 weeks); below this a % change is noise
MIN_ABS_Z = 1.5              # |robust z| needed before a move is labelled rising/falling (else 'steady')
MIN_BASELINE_WEEKS = 3       # of the 4 prior weeks
MIN_HISTORY_WEEKS = 8
RISING_PCT = 25.0
FALLING_PCT = -25.0


def compute_momentum(weekly: Mapping[date, int], last_week: Optional[date] = None) -> Dict[str, Any]:
    """weekly: {week_start: total views}. last_week defaults to the newest week present."""
    out: Dict[str, Any] = {"views_7d": None, "views_28d_avg_weekly": None, "momentum_pct": None, "label": None,
                           "robust_z": None, "weeks_of_history": len(weekly)}
    if not weekly:
        return out
    last_week = last_week or max(weekly)
    if last_week not in weekly:
        return out                       # no observation for the latest week: do not compare stale data
    cur = weekly[last_week]
    out["views_7d"] = cur
    prior = [weekly[last_week - timedelta(weeks=i)] for i in range(1, 5) if (last_week - timedelta(weeks=i)) in weekly]
    if len(prior) >= MIN_BASELINE_WEEKS:
        base = mean(prior)
        out["views_28d_avg_weekly"] = round(base, 1)
        if base >= MIN_BASELINE:
            pct = 100.0 * (cur - base) / base
            out["momentum_pct"] = round(pct, 1)
            out["label"] = "rising" if pct >= RISING_PCT else ("falling" if pct <= FALLING_PCT else "steady")
    hist = [v for w, v in weekly.items() if w < last_week]
    if len(hist) >= MIN_HISTORY_WEEKS:
        med = median(hist)
        mad = median(abs(v - med) for v in hist)
        scale = max(mad, 0.05 * med, 1.0)
        out["robust_z"] = round(0.6745 * (cur - med) / scale, 2)
    if out["label"] in ("rising", "falling") and (out["robust_z"] is None or abs(out["robust_z"]) < MIN_ABS_Z):
        out["label"] = "steady"          # a % change inside the entity's normal weekly noise is not a trend
    return out


def rank_momentum(rows: List[Dict[str, Any]], limit: int) -> Dict[str, List[Dict[str, Any]]]:
    """rows: dicts carrying momentum_pct. Top risers (desc) and fallers (asc); NULL momentum excluded."""
    have = [r for r in rows if r.get("momentum_pct") is not None and (("label" not in r) or r["label"] in ("rising", "falling"))]
    risers = sorted((r for r in have if r["momentum_pct"] > 0), key=lambda r: (-r["momentum_pct"], r.get("name") or ""))[:limit]
    fallers = sorted((r for r in have if r["momentum_pct"] < 0), key=lambda r: (r["momentum_pct"], r.get("name") or ""))[:limit]
    return {"risers": risers, "fallers": fallers}


async def momentum_for_market(session, market_clause_expr, limit: int = 10) -> Dict[str, Any]:
    """Top risers/fallers among active entities in a market, from entity_attention_weekly."""
    from sqlalchemy import select, text
    from app.models.entity import Entity
    ents = (await session.execute(select(Entity.id, Entity.name, Entity.entity_type, Entity.category)
                                  .where(Entity.status == "active").where(market_clause_expr))).all()
    meta = {e.id: e for e in ents}
    res = await session.execute(text("SELECT entity_id, week_start, total FROM entity_attention_weekly WHERE entity_id = ANY(:ids)"),
                                {"ids": list(meta)})
    weekly: Dict[Any, Dict[date, int]] = {}
    for eid, w, t in res.all():
        weekly.setdefault(eid, {})[w] = t
    as_of = max((max(v) for v in weekly.values()), default=None)
    rows = []
    for eid, wk in weekly.items():
        m = compute_momentum(wk, as_of)
        e = meta[eid]
        rows.append({"entity_id": str(eid), "name": e.name, "entity_type": e.entity_type, "category": e.category, **m})
    ranked = rank_momentum(rows, limit)
    return {"as_of_week": as_of.isoformat() if as_of else None, "entities_with_history": len(weekly),
            "entities_with_momentum": sum(1 for r in rows if r["momentum_pct"] is not None),
            "formula": {"momentum_pct": "(views_7d - mean(prior 4 weeks)) / mean(prior 4 weeks) * 100",
                        "min_baseline_views_per_week": MIN_BASELINE, "rising_pct": RISING_PCT, "falling_pct": FALLING_PCT, "min_abs_robust_z": MIN_ABS_Z,
                        "source": "Wikipedia en+hi user pageviews, complete ISO weeks (entity_attention_weekly)"},
            **ranked}

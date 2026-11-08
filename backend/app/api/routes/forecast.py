"""
LiveIQ — Demand Forecasting (Sprint 6C)
Time-series forecast of an entity's Google Trends interest using Facebook
Prophet, so bookers can see whether demand for an artist is trending up
or down heading into a proposed event window.

Endpoint:
  GET /intelligence/{entity_id}/forecast?city=Mumbai&months=6

Data reality check (as of this feature's addition): entity_metrics.py
collects at most a few snapshots per entity over ~2 weeks of real
history — nowhere near enough for Prophet to detect genuine trend or
seasonality. Rather than run Prophet on 2-5 points and present a
confident-looking chart built on noise, this endpoint enforces a real
minimum-history gate and returns an explicit "insufficient_history"
status (not a fabricated forecast) when an entity doesn't have enough
real data points yet. As entity_metrics.py keeps running on its 6-hour
schedule, entities will cross the threshold and get real forecasts
without any code change here.
"""

import asyncio
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.api.deps import get_current_user
from app.models.user import User

try:
    import pandas as pd
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

router = APIRouter()
logger = structlog.get_logger()

# Prophet can technically fit on 2 points, but the output is meaningless
# noise-fitting, not a forecast. This is a real minimum for a trend line
# to mean anything, still modest given weekly-ish collection cadence.
MIN_HISTORY_POINTS = 10
MIN_HISTORY_DAYS_SPAN = 21  # also require the points to span enough calendar time


@router.get("/{entity_id}/forecast", summary="Google Trends demand forecast for an entity")
async def forecast_demand(
    entity_id: str,
    city: Optional[str] = Query(None, description="City context (informational — forecast is entity-level, not city-specific yet)"),
    months: int = Query(3, ge=1, le=12, description="Months ahead to forecast"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        uid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity_result = await db.execute(select(Entity).where(Entity.id == uid))
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    metrics_result = await db.execute(
        select(EntityMetric.time, EntityMetric.google_trend_score)
        .where(EntityMetric.entity_id == uid, EntityMetric.google_trend_score.isnot(None))
        .order_by(asc(EntityMetric.time))
    )
    rows = metrics_result.all()

    history = [{"date": t.date().isoformat(), "google_trend_score": score} for t, score in rows]

    span_days = (rows[-1][0] - rows[0][0]).days if len(rows) >= 2 else 0

    if len(rows) < MIN_HISTORY_POINTS or span_days < MIN_HISTORY_DAYS_SPAN:
        return {
            "entity": {"id": entity_id, "name": entity.name},
            "city": city,
            "status": "insufficient_history",
            "history": history,
            "history_points": len(rows),
            "history_span_days": span_days,
            "minimum_required": {"points": MIN_HISTORY_POINTS, "span_days": MIN_HISTORY_DAYS_SPAN},
            "forecast": None,
            "message": (
                f"Only {len(rows)} tracked data point(s) spanning {span_days} day(s) exist for this entity — "
                f"Prophet needs at least {MIN_HISTORY_POINTS} points across {MIN_HISTORY_DAYS_SPAN}+ days to "
                "detect a real trend. Returning no forecast rather than fitting a curve to noise. Check back "
                "as entity_metrics.py accumulates more history on its scheduled runs."
            ),
        }

    if not PROPHET_AVAILABLE:
        raise HTTPException(503, "Prophet is not installed on this server — forecasting unavailable")

    # Prophet requires tz-naive timestamps — DB values are tz-aware (UTC).
    df = pd.DataFrame([{"ds": t.replace(tzinfo=None), "y": score} for t, score in rows])

    def _fit_predict():
        model = Prophet(
            yearly_seasonality=False,   # not enough history to detect yearly patterns honestly
            weekly_seasonality=len(rows) >= 14,
            daily_seasonality=False,
            interval_width=0.80,
        )
        model.fit(df)
        future = model.make_future_dataframe(periods=months * 30, freq="D")
        return model.predict(future)

    try:
        # Prophet's Stan fit is CPU-bound and blocks for seconds — keep it off the event loop.
        forecast_df = await asyncio.to_thread(_fit_predict)
    except Exception as exc:
        logger.warning("forecast_demand: Prophet fit/predict failed", entity=entity.name, error=str(exc))
        raise HTTPException(500, f"Forecast model failed to fit this entity's data: {exc}")

    future_only = forecast_df[forecast_df["ds"] > df["ds"].max()]
    forecast_points = [
        {
            "date": row.ds.date().isoformat(),
            "predicted_trend_score": round(max(0.0, row.yhat), 1),
            "lower_bound": round(max(0.0, row.yhat_lower), 1),
            "upper_bound": round(max(0.0, row.yhat_upper), 1),
        }
        for row in future_only.itertuples()
    ]

    first_val = float(df["y"].iloc[0])
    last_val = float(df["y"].iloc[-1])
    history_trend = "rising" if last_val > first_val * 1.1 else "falling" if last_val < first_val * 0.9 else "stable"
    # Direction of the PROJECTION: where the forecast ends vs the recent level (mean of the last
    # 3 observations, so one noisy reading can't flip it). Previously this reported the
    # history's first-vs-last move, which could contradict the forecast line shown beside it.
    recent = float(df["y"].tail(3).mean())
    end_val = forecast_points[-1]["predicted_trend_score"] if forecast_points else recent
    trend_direction = (
        "rising" if end_val > recent * 1.1 else "falling" if end_val < recent * 0.9 else "stable"
    )

    return {
        "entity": {"id": entity_id, "name": entity.name},
        "city": city,
        "status": "ok",
        "history": history,
        "history_points": len(rows),
        "history_span_days": span_days,
        "trend_direction": trend_direction,
        "history_trend_direction": history_trend,
        "forecast": forecast_points,
        "methodology": (
            f"Facebook Prophet fit on {len(rows)} real google_trend_score snapshots spanning "
            f"{span_days} days (source: entity_metrics.py, Google Trends via pytrends). Weekly "
            f"seasonality {'enabled' if len(rows) >= 14 else 'disabled (not enough history)'}; "
            "yearly seasonality disabled — no entity has a full year of history yet. 80% confidence "
            "interval shown. This is a statistical projection from limited real data, not a guarantee."
        ),
    }

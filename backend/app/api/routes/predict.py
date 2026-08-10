"""
LiveIQ — Event Success Predictor (M8)
Sell-out probability (classification-style read) and revenue prediction,
per IMPLEMENTATION_PLAN.md's M8 spec. Both endpoints delegate to the
exact same real P&L computation events.py's /events/model already runs
(_compute_deal_model — entity composite_score, city demand, the trained
GradientBoostingRegressor pricing/fill-rate model, real artist_fee data
where available) rather than a second, independent model that could
disagree with it. See app/services/ml/pricing_engine.py for the model's
real synthetic-training-data disclosure.

Endpoints:
  POST /predict/event-success  → sell-out probability + fill-rate read
  POST /predict/revenue        → expected/conservative/optimistic revenue
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_roles
from app.models.user import User, UserRole
from app.api.routes.events import DealModelRequest, _compute_deal_model

router = APIRouter()


def _sellout_probability(predicted_fill_rate_pct: float, confidence_pct: float, model_name: str) -> dict:
    """
    Real classification-style read derived from the same fill-rate number
    /events/model already produces — not a separately-trained classifier.
    Bands are stated plainly (>=90% fill treated as "sold out" territory,
    matching Event.status's own EventStatus.SOLD_OUT convention elsewhere
    in this codebase) rather than invented to look precise.
    """
    if predicted_fill_rate_pct >= 90:
        probability_band = "high"
    elif predicted_fill_rate_pct >= 70:
        probability_band = "moderate"
    else:
        probability_band = "low"

    # A crude but real confidence-weighted probability estimate: the fill
    # rate itself IS the model's estimate of demand saturation, so we use
    # it directly as the sell-out probability, damped by the model's own
    # stated confidence (a low-confidence 95% fill-rate prediction is a
    # less trustworthy "high" than a high-confidence one).
    raw_probability = min(99.0, predicted_fill_rate_pct * (confidence_pct / 100))

    # _compute_deal_model (events.py) silently falls back to a rule-based
    # fill-rate estimate when the trained GBR model is unavailable
    # (sklearn missing, load/predict failure) — that fallback is fine for
    # /events/model, but this endpoint's whole framing is "a real
    # classification-style read," so if the number underneath it is the
    # cruder rule-based one, that must be said here too, not just implied
    # by an opaque "model" field the caller might not inspect.
    methodology = (
        "Derived directly from the pricing engine's predicted_fill_rate, "
        "damped by its own confidence score — not a separately trained "
        "sell-out classifier. A 95%+ fill rate is treated as the sold-out threshold."
    )
    if model_name != "ml_gbr":
        methodology += " NOTE: the trained ML model was unavailable for this request — predicted_fill_rate came from the cruder rule-based fallback, so this sellout read is correspondingly less reliable."

    return {
        "sellout_probability_pct": round(raw_probability, 1),
        "probability_band": probability_band,
        "based_on_ml_model": model_name == "ml_gbr",
        "methodology": methodology,
    }


@router.post("/event-success", summary="Predict sell-out probability + fill rate for a proposed booking")
async def predict_event_success(
    request: DealModelRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.EXECUTIVE, UserRole.ANALYST, UserRole.BOOKER)),
):
    deal = await _compute_deal_model(request, db)
    sellout = _sellout_probability(
        deal["prediction"]["predicted_fill_rate_pct"],
        deal["prediction"]["confidence_pct"],
        deal["prediction"]["model"],
    )
    return {
        "entity": deal["entity"],
        "venue": deal["venue"],
        "prediction": deal["prediction"],
        "sellout": sellout,
        "risk_level": deal["risk_level"],
        "market_context": deal["market_context"],
    }


@router.post("/revenue", summary="Predict expected/conservative/optimistic gross revenue")
async def predict_revenue(
    request: DealModelRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.EXECUTIVE, UserRole.ANALYST, UserRole.BOOKER)),
):
    deal = await _compute_deal_model(request, db)
    return {
        "entity": deal["entity"],
        "venue": deal["venue"],
        "scenarios": deal["scenarios"],
        "break_even": deal["break_even"],
        "artist_fee": deal["artist_fee"],
        "cost_model_note": deal["cost_model_note"],
        "risk_level": deal["risk_level"],
    }

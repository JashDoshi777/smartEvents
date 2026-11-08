"""
LiveIQ — Event Deal Modeler (Sprint 5C)
Full P&L simulation for a proposed booking: artist + city + venue + price
→ predicted fill rate, revenue at 3 fill-rate scenarios, cost breakdown,
break-even ticket count, and a risk read.

Endpoint:
  POST /events/model
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.city import City
from app.models.venue import Venue
from app.models.event import Event
from app.api.deps import require_roles, get_current_user
from app.models.user import User, UserRole
from app.services.city_lookup import resolve_city, escape_like

try:
    from app.services.ml.pricing_engine import pricing_engine
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    pricing_engine = None  # type: ignore

router = APIRouter()
logger = structlog.get_logger()


# ── Cost model — industry rule-of-thumb, clearly disclosed as an estimate ──
# No real venue-rental or ops-cost data exists in the DB (only artist
# booking fee is a real field). These percentages are triangulated from
# Western touring-industry conventions (Pollstar/IEBA-style trade sources,
# general event-budgeting guides) — NOT India-specific audited figures.
# They are surfaced to the user as an explicit estimate with the formula
# shown, never presented as a measured number.
VENUE_COST_PCT_OF_REVENUE = 0.10   # range cited: 5-15%
OPS_COST_PCT_OF_REVENUE = 0.25     # range cited: 20-35% (security, staffing, marketing, production, insurance)
COST_MODEL_NOTE = (
    "Venue (~10% of gross) and operations (~25% of gross — security, staffing, "
    "marketing, production, insurance) are industry rule-of-thumb estimates, not "
    "measured figures — no real cost data exists for these yet. Artist fee is a "
    "real range from the entity's booking_price_range."
)


class DealModelRequest(BaseModel):
    entity_id: str = Field(..., description="UUID of the artist/entity to book")
    city: str = Field(..., description="City where the event will be held")
    venue_id: Optional[str] = Field(None, description="UUID of a specific venue; omit to use venue_capacity directly")
    venue_capacity: Optional[int] = Field(None, ge=100, le=100000, description="Venue capacity if not selecting a specific venue")
    ticket_price: float = Field(..., ge=100, le=50000, description="Proposed average ticket price (INR)")
    lead_days: int = Field(60, ge=1, le=730, description="Days between booking and event date")


def _fmt_inr(n: float) -> str:
    return f"₹{n:,.0f}"


async def _compute_deal_model(request: "DealModelRequest", db: AsyncSession) -> dict:
    """
    The actual P&L simulation — factored out of the route handler so
    /predict/event-success and /predict/revenue (predict.py) can call the
    exact same real computation instead of re-deriving fill-rate/revenue
    logic a second time and risking the two disagreeing.
    """
    # ── Resolve entity ──────────────────────────────────────────────────────
    try:
        entity_uid = UUID(request.entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity_result = await db.execute(select(Entity).where(Entity.id == entity_uid))
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, f"Entity '{request.entity_id}' not found")

    # ── Resolve venue (optional — capacity can be given directly) ──────────
    venue: Optional[Venue] = None
    if request.venue_id:
        try:
            venue_uid = UUID(request.venue_id)
        except ValueError:
            raise HTTPException(400, "Invalid venue_id format")
        venue_result = await db.execute(select(Venue).where(Venue.id == venue_uid))
        venue = venue_result.scalar_one_or_none()
        if not venue:
            raise HTTPException(404, f"Venue '{request.venue_id}' not found")

    capacity = venue.total_capacity if venue else request.venue_capacity
    if not capacity:
        if venue is not None:
            raise HTTPException(400, f"Venue '{venue.name}' has no capacity on file — provide venue_capacity manually.")
        raise HTTPException(400, "Provide either venue_id or venue_capacity")

    # ── Resolve city market score ────────────────────────────────────────────
    city_obj = await resolve_city(db, request.city)
    city_name = city_obj.name if city_obj else request.city.strip()
    city_like = escape_like(city_name)
    city_music_score = city_obj.music_market_size if city_obj and city_obj.music_market_size is not None else 70.0

    # ── Latest composite score for this entity ──────────────────────────────
    metric_result = await db.execute(
        select(EntityMetric)
        .where(EntityMetric.entity_id == entity_uid, EntityMetric.composite_score.isnot(None))
        .order_by(desc(EntityMetric.time))
        .limit(1)
    )
    metric = metric_result.scalar_one_or_none()
    composite_score = (metric.composite_score or 30.0) if metric else 30.0
    has_live_metrics = metric is not None

    # ── Sprint 6A features: real DB-derived market-saturation signals ──────
    # Neither venue_id/venue_capacity input carries a specific event date —
    # only lead_days — so the target date is derived as today + lead_days,
    # giving a real (if request-time-relative) calendar anchor for both
    # the "days since last event in this city" and "same weekend" queries.
    target_date = datetime.now(timezone.utc) + timedelta(days=request.lead_days)
    weekend_start = target_date - timedelta(days=3)
    weekend_end = target_date + timedelta(days=3)

    last_event_result = await db.execute(
        select(func.max(Event.event_date))
        .join(Venue, Event.venue_id == Venue.id)
        .where(Venue.city.ilike(city_like, escape="\\"), Event.event_date < target_date)
    )
    last_event_date = last_event_result.scalar_one_or_none()
    if last_event_date is not None:
        if last_event_date.tzinfo is None:
            last_event_date = last_event_date.replace(tzinfo=timezone.utc)
        days_since_last_event = max(0.0, (target_date - last_event_date).days)
    else:
        days_since_last_event = None

    competitor_count_result = await db.execute(
        select(func.count())
        .select_from(Event)
        .join(Venue, Event.venue_id == Venue.id)
        .where(
            Venue.city.ilike(city_like, escape="\\"),
            Event.event_date >= weekend_start,
            Event.event_date <= weekend_end,
        )
    )
    competitor_events_same_weekend = float(competitor_count_result.scalar_one() or 0)

    # ── Master-data feature: PredictHQ real demand-significance signals ─────
    # Real comparable events (any source) in this city/date window that
    # carry a PredictHQ rank — averaged into a single feature. Also
    # surfaced directly in the response as an honest external cross-check,
    # not folded silently into the fill-rate number: this is a real,
    # independently-sourced significance signal for the SAME window, not
    # a measurement of this specific proposed event.
    phq_result = await db.execute(
        select(Event.predicthq_rank, Event.predicthq_local_rank, Event.predicthq_predicted_attendance, Event.title)
        .join(Venue, Event.venue_id == Venue.id, isouter=True)
        .where(
            Event.predicthq_rank.isnot(None),
            Event.event_date >= weekend_start,
            Event.event_date <= weekend_end,
        )
        .limit(20)
    )
    phq_rows = phq_result.all()
    phq_ranks = [r.predicthq_rank for r in phq_rows if r.predicthq_rank is not None]
    phq_attendances = [r.predicthq_predicted_attendance for r in phq_rows if r.predicthq_predicted_attendance is not None]
    phq_avg_rank = (sum(phq_ranks) / len(phq_ranks)) if phq_ranks else None
    predicthq_context = {
        "comparable_events_found": len(phq_rows),
        "avg_rank": round(phq_avg_rank, 1) if phq_avg_rank is not None else None,
        "avg_predicted_attendance": round(sum(phq_attendances) / len(phq_attendances)) if phq_attendances else None,
        "source": "PredictHQ — real events in the same date window (not city-filtered; PredictHQ events aren't yet resolved to a specific tracked city)",
    }

    # ── ML fill-rate prediction (reuses the same trained pricing engine) ────
    if ML_AVAILABLE and pricing_engine is not None:
        ml_result = pricing_engine.predict(
            composite_score=composite_score,
            city_music_score=city_music_score,
            venue_capacity=capacity,
            proposed_price=request.ticket_price,
            category=(entity.category or "music"),
            is_international=entity.is_international or False,
            lead_days=request.lead_days,
            days_since_last_event_in_city=days_since_last_event,
            competitor_events_same_weekend=competitor_events_same_weekend,
            phq_avg_rank=phq_avg_rank,
        )
        predicted_fill_pct = ml_result["predicted_fill_rate"]
        model_name = ml_result["model"]
        confidence = ml_result["confidence"]
        # Audit finding: every other estimated value in this response is
        # labeled (artist_fee.source, cost_model_note), but the model's
        # synthetic-vs-real training basis wasn't reaching the API
        # consumer at all — surface it explicitly rather than only via
        # code comments/docstrings no caller can see.
        model_data_source = ml_result.get("meta", {}).get("data_source", "synthetic")
    else:
        predicted_fill_pct = round(min(95, composite_score * 0.9), 1)
        model_name = "rule_based"
        confidence = 50
        model_data_source = None

    # ── Artist fee: real range from the entity, midpoint as the point estimate ──
    fee_min = entity.booking_price_range_min
    fee_max = entity.booking_price_range_max
    if fee_min is not None and fee_max is not None:
        artist_fee = (fee_min + fee_max) / 2
        artist_fee_source = "real"
    else:
        # No booking-fee data for this entity — fall back to a composite-
        # score-scaled placeholder, clearly labeled as such, never silently
        # treated as real. composite_score is nominally 0-100 but isn't
        # re-validated by this endpoint, so clamp defensively before scaling.
        clamped_score = max(0.0, min(100.0, composite_score))
        artist_fee = 500_000 * (clamped_score / 50.0)
        artist_fee_source = "estimated (no booking_price_range on file for this entity)"

    # ── P&L at 3 fill-rate scenarios ─────────────────────────────────────────
    def _scenario(fill_pct: float) -> dict:
        attendance = round(capacity * fill_pct / 100)
        gross_revenue = attendance * request.ticket_price
        venue_cost = gross_revenue * VENUE_COST_PCT_OF_REVENUE
        ops_cost = gross_revenue * OPS_COST_PCT_OF_REVENUE
        total_cost = artist_fee + venue_cost + ops_cost
        net_profit = gross_revenue - total_cost
        margin_pct = round((net_profit / gross_revenue) * 100, 1) if gross_revenue > 0 else None
        return {
            "fill_rate_pct": fill_pct,
            "attendance": attendance,
            "gross_revenue": round(gross_revenue),
            "gross_revenue_fmt": _fmt_inr(gross_revenue),
            "artist_fee": round(artist_fee),
            "venue_cost": round(venue_cost),
            "ops_cost": round(ops_cost),
            "total_cost": round(total_cost),
            "net_profit": round(net_profit),
            "net_profit_fmt": _fmt_inr(net_profit),
            "margin_pct": margin_pct,
        }

    # Keep conservative <= expected <= optimistic even at the extremes (a 2% expected fill
    # used to produce a 5% "conservative" case; a 99.5% one a 99% "optimistic" case).
    expected_fill = max(0.0, min(100.0, predicted_fill_pct))
    conservative_fill = min(expected_fill, max(5, round(expected_fill * 0.7, 1)))
    optimistic_fill = max(expected_fill, min(99, round(expected_fill * 1.2, 1)))

    scenarios = {
        "conservative": _scenario(conservative_fill),
        "expected": _scenario(expected_fill),
        "optimistic": _scenario(optimistic_fill),
    }

    # ── Break-even: minimum attendance where gross revenue == total fixed cost ──
    # (venue/ops costs are modeled as % of revenue, so break-even attendance
    # solves: price*N = fee + (price*N)*(venue_pct+ops_pct)
    #     =>  N = fee / (price * (1 - venue_pct - ops_pct))
    variable_retained_pct = 1 - VENUE_COST_PCT_OF_REVENUE - OPS_COST_PCT_OF_REVENUE
    break_even_tickets = None
    break_even_fill_pct = None
    break_even_achievable = False
    if request.ticket_price > 0 and variable_retained_pct > 0:
        break_even_tickets = round(artist_fee / (request.ticket_price * variable_retained_pct))
        # Uncapped — a break-even fill rate over 100% means the deal cannot
        # break even at this venue/price at all, which is exactly what the
        # booker needs to see, not a number silently clamped to look feasible.
        break_even_fill_pct = round((break_even_tickets / capacity) * 100, 1)
        break_even_achievable = break_even_tickets <= capacity

    # ── Risk read ─────────────────────────────────────────────────────────
    expected_net = scenarios["expected"]["net_profit"]
    conservative_net = scenarios["conservative"]["net_profit"]
    if conservative_net > 0:
        risk_level = "Low"
    elif expected_net > 0:
        risk_level = "Medium"
    else:
        risk_level = "High"

    return {
        "entity": {
            "id": request.entity_id,
            "name": entity.name,
            "category": entity.category,
            "is_international": entity.is_international or False,
            "composite_score": round(composite_score, 1),
            "has_live_metrics": has_live_metrics,
        },
        "venue": {
            "id": request.venue_id,
            "name": venue.name if venue else None,
            "city": city_name,
            "capacity": capacity,
        },
        "inputs": {
            "ticket_price": request.ticket_price,
            "lead_days": request.lead_days,
        },
        "prediction": {
            "predicted_fill_rate_pct": predicted_fill_pct,
            "model": model_name,
            "confidence_pct": confidence,
            "model_data_source": model_data_source,
        },
        "artist_fee": {
            "amount": round(artist_fee),
            "amount_fmt": _fmt_inr(artist_fee),
            "range_min": fee_min,
            "range_max": fee_max,
            "source": artist_fee_source,
        },
        "scenarios": scenarios,
        "break_even": {
            "tickets": break_even_tickets,
            "fill_rate_pct": break_even_fill_pct,
            "achievable": break_even_achievable,
        },
        "risk_level": risk_level,
        "cost_model": {"venue_pct": VENUE_COST_PCT_OF_REVENUE, "ops_pct": OPS_COST_PCT_OF_REVENUE},
        "cost_model_note": COST_MODEL_NOTE,
        "market_context": {
            "predicthq": predicthq_context,
        },
    }


@router.post("/model", summary="Full P&L simulation for a proposed event booking")
async def model_event_deal(
    request: DealModelRequest,
    db: AsyncSession = Depends(get_db),
    # Per ARCHITECTURE_AND_APP_STRUCTURE.md §9: the Revenue Simulator /
    # Event Deal Modeler is Booker + Analyst + Executive territory —
    # Marketing and Viewer roles aren't meant to run deal simulations.
    user: User = Depends(require_roles(UserRole.EXECUTIVE, UserRole.ANALYST, UserRole.BOOKER)),
):
    return await _compute_deal_model(request, db)


def _ist_day(d: str, end: bool = False):
    """YYYY-MM-DD (an India calendar day) -> UTC instant of that day's start (or the next day's start)."""
    try:
        day = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    except ValueError:
        raise HTTPException(422, f"Invalid date '{d}' — use YYYY-MM-DD")
    return (day + timedelta(days=1)) if end else day


def _event_filters(source, city, category, q, when, now, date_from=None, date_to=None):
    conds = []
    if date_from:
        conds.append(Event.event_date >= _ist_day(date_from))
    if date_to:
        conds.append(Event.event_date < _ist_day(date_to, end=True))
    if source:
        conds.append(Event.source == source)
    if category:
        conds.append(Event.category == category)
    if city:
        conds.append(Venue.city.ilike(escape_like(city.replace("-", " ").strip()), escape="\\"))
    if q and q.strip():
        conds.append(Event.title.ilike(f"%{escape_like(q.strip())}%", escape="\\"))
    # "upcoming" is derived from the date, not the stored status (which goes stale: rows
    # synced as "upcoming" stay that way after the date passes).
    if when == "upcoming":
        conds.append(Event.event_date >= now)
    elif when == "past":
        conds.append(Event.event_date < now)
    return conds


@router.get("/summary", summary="Aggregates over ALL events (not just one page)")
async def events_summary(
    source: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
    when: str = Query("all", pattern="^(all|upcoming|past)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    conds = _event_filters(source, city, category, q, when, now)
    base = select(Event).outerjoin(Venue, Event.venue_id == Venue.id).where(*conds).subquery()

    async def groups(col):
        rows = (await db.execute(select(col, func.count()).select_from(base).group_by(col))).all()
        return rows

    total = await db.scalar(select(func.count()).select_from(base)) or 0
    upcoming = await db.scalar(select(func.count()).select_from(base).where(base.c.event_date >= now)) or 0
    within30 = await db.scalar(select(func.count()).select_from(base).where(base.c.event_date >= now, base.c.event_date < now + timedelta(days=30))) or 0
    with_fill = await db.scalar(select(func.count()).select_from(base).where(base.c.fill_rate.isnot(None))) or 0
    no_venue = await db.scalar(select(func.count()).select_from(base).where(base.c.venue_id.is_(None))) or 0
    month_expr = func.to_char(func.timezone("Asia/Kolkata", base.c.event_date), "YYYY-MM")
    by_month = (await db.execute(select(month_expr, func.count()).select_from(base).where(base.c.event_date.isnot(None)).group_by(month_expr).order_by(month_expr))).all()
    by_category = await groups(base.c.category)
    by_source = await groups(base.c.source)
    by_city = (await db.execute(
        select(Venue.city, func.count()).select_from(base).outerjoin(Venue, base.c.venue_id == Venue.id).group_by(Venue.city)
    )).all()
    # Facets for the filter UI are computed WITHOUT the filters so options never vanish.
    fac_src = (await db.execute(select(Event.source, func.count()).group_by(Event.source))).all()
    fac_cat = (await db.execute(select(Event.category, func.count()).group_by(Event.category))).all()
    fac_city = (await db.execute(select(Venue.city, func.count()).select_from(Event).join(Venue, Event.venue_id == Venue.id).group_by(Venue.city))).all()

    def d(rows):
        return sorted(({"key": k, "count": n} for k, n in rows if k), key=lambda r: (-r["count"], r["key"]))

    return {
        "total": total, "upcoming": upcoming, "past": total - upcoming, "next_30_days": within30,
        "with_fill_rate": with_fill, "without_venue": no_venue,
        "by_month": [{"month": m, "count": n} for m, n in by_month],
        "by_category": d(by_category), "by_source": d(by_source), "by_city": d(by_city),
        "facets": {"sources": d(fac_src), "categories": d(fac_cat), "cities": d(fac_city)},
        "timezone": "Asia/Kolkata",
        "as_of": now.isoformat(),
    }


@router.get("", summary="List events (upcoming first), with city/venue when known")
async def list_events(
    limit: int = 100,
    offset: int = 0,
    source: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    q: Optional[str] = Query(None, max_length=120),
    when: str = Query("all", pattern="^(all|upcoming|past)$"),
    date_from: Optional[str] = Query(None, description="IST day, YYYY-MM-DD (inclusive)"),
    date_to: Optional[str] = Query(None, description="IST day, YYYY-MM-DD (inclusive)"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = max(1, min(limit, 500))
    now = datetime.now(timezone.utc)
    conds = _event_filters(source, city, category, q, when, now, date_from, date_to)
    sort = Event.event_date.asc().nullslast() if order == "asc" else Event.event_date.desc().nullslast()
    qry = (
        select(Event, Venue.name, Venue.city)
        .outerjoin(Venue, Event.venue_id == Venue.id)
        .where(*conds)
        .order_by(sort, Event.id.asc())
        .limit(limit)
        .offset(max(offset, 0))
    )
    rows = (await db.execute(qry)).all()
    total = await db.scalar(select(func.count()).select_from(Event).outerjoin(Venue, Event.venue_id == Venue.id).where(*conds)) or 0
    return {
        "total": total,
        "events": [
            {
                "id": str(e.id),
                "title": e.title,
                "category": e.category,
                "source": e.source,
                "status": e.status,
                "is_upcoming": bool(e.event_date and e.event_date >= now),
                "event_date": e.event_date.isoformat() if e.event_date else None,
                "venue": vname,
                "city": vcity,
                "ticket_price_min": float(e.ticket_price_min) if e.ticket_price_min is not None else None,
                "ticket_price_max": float(e.ticket_price_max) if e.ticket_price_max is not None else None,
                "total_capacity": e.total_capacity,
                "tickets_sold": e.tickets_sold,
                "fill_rate": e.fill_rate,
                "booking_url": e.booking_url,
            }
            for e, vname, vcity in rows
        ],
    }

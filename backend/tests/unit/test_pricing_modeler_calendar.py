"""Accuracy invariants for the pricing engine, deal modeler P&L and venue-calendar bucketing."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.ml.pricing_engine import pricing_engine
from app.services.city_lookup import escape_like, norm_city


def predict(**kw):
    base = dict(composite_score=50, city_music_score=80, venue_capacity=5000, proposed_price=2500,
                category="music", is_international=False, lead_days=60)
    base.update(kw)
    return pricing_engine.predict(**base)


@pytest.mark.parametrize("cap", [100, 500, 5000, 50000, 100000])
@pytest.mark.parametrize("price", [100, 800, 2500, 12000, 50000])
@pytest.mark.parametrize("score", [0, 20, 50, 95])
def test_engine_bounds(cap, price, score):
    r = predict(venue_capacity=cap, proposed_price=price, composite_score=score)
    assert 0 <= r["predicted_fill_rate"] <= 100
    assert 299 <= r["recommended_price"] <= 50000
    assert all(0 <= p["attendance_pct"] <= 100 for p in r["sensitivity_curve"])


def test_engine_fill_monotonic_in_price_and_curve_consistent():
    r = predict()
    if r["model"] != "ml_gbr":
        pytest.skip("rule-based fallback has no curve")
    fills = [p["attendance_pct"] for p in r["sensitivity_curve"]]
    assert fills == sorted(fills, reverse=True), "higher price must never raise fill"
    at_proposed = next(p for p in r["sensitivity_curve"] if p["price"] == 2500)
    assert at_proposed["attendance_pct"] == r["predicted_fill_rate"]


def test_engine_price_moves_fill():
    lo, hi = predict(proposed_price=1000), predict(proposed_price=9000)
    if lo["model"] == "ml_gbr":
        assert lo["predicted_fill_rate"] >= hi["predicted_fill_rate"]


def test_city_lookup_helpers():
    assert escape_like("50%_x") == r"50\%\_x"
    assert norm_city("Delhi-NCR ") == "delhi ncr"


# ── Deal modeler arithmetic ──────────────────────────────────────────────────
class _Res:
    def __init__(self, v):
        self.v = v
    def scalar_one_or_none(self): return self.v
    def scalar_one(self): return self.v
    def scalars(self): return SimpleNamespace(first=lambda: self.v)
    def all(self): return self.v if isinstance(self.v, list) else []


class _FakeDb:
    def __init__(self, results):
        self.results = list(results)
    async def execute(self, *_a, **_k):
        return _Res(self.results.pop(0))


def _entity(fee_min=500_000, fee_max=1_500_000):
    return SimpleNamespace(id="x", name="Test Act", category="music", is_international=False,
                           booking_price_range_min=fee_min, booking_price_range_max=fee_max)


def _model(price, capacity, fee=(500_000, 1_500_000)):
    from app.api.routes.events import DealModelRequest, _compute_deal_model
    import uuid
    req = DealModelRequest(entity_id=str(uuid.uuid4()), city="Mumbai", venue_capacity=capacity, ticket_price=price, lead_days=60)
    city = SimpleNamespace(name="Mumbai", music_market_size=90.0)
    metric = SimpleNamespace(composite_score=60.0)
    db = _FakeDb([_entity(*fee), city, metric, None, 0, []])
    return asyncio.run(_compute_deal_model(req, db))


@pytest.mark.parametrize("price,cap", [(100, 100), (500, 300), (2500, 5000), (50000, 100000), (1200, 800)])
def test_modeler_pnl_arithmetic(price, cap):
    m = _model(price, cap)
    fee = m["artist_fee"]["amount"]
    assert fee == 1_000_000  # midpoint of the real range, in ₹
    sc = m["scenarios"]
    assert sc["conservative"]["fill_rate_pct"] <= sc["expected"]["fill_rate_pct"] <= sc["optimistic"]["fill_rate_pct"]
    for s in sc.values():
        assert 0 <= s["fill_rate_pct"] <= 100
        assert s["attendance"] == round(cap * s["fill_rate_pct"] / 100)
        assert s["attendance"] <= cap
        assert abs(s["gross_revenue"] - s["attendance"] * price) <= 1
        assert abs(s["venue_cost"] - 0.10 * s["gross_revenue"]) <= 1
        assert abs(s["ops_cost"] - 0.25 * s["gross_revenue"]) <= 1
        assert abs(s["total_cost"] - (fee + s["venue_cost"] + s["ops_cost"])) <= 2
        assert abs(s["net_profit"] - (s["gross_revenue"] - s["total_cost"])) <= 2
        if s["gross_revenue"] > 0:
            assert abs(s["margin_pct"] - s["net_profit"] / s["gross_revenue"] * 100) < 0.2
    be = m["break_even"]
    assert be["tickets"] == round(fee / (price * 0.65))
    assert be["achievable"] == (be["tickets"] <= cap)
    # at break-even attendance, net is ~0
    gross = be["tickets"] * price
    assert abs(gross - (fee + 0.35 * gross)) <= price  # within one ticket of rounding


def test_modeler_higher_price_not_free_money():
    """Fill must fall as price rises (previously fill was price-independent)."""
    lo, hi = _model(800, 5000), _model(8000, 5000)
    if lo["prediction"]["model"] == "ml_gbr":
        assert lo["prediction"]["predicted_fill_rate_pct"] >= hi["prediction"]["predicted_fill_rate_pct"]

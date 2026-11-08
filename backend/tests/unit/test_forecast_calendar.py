import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.routes.forecast import forecast_demand
from app.api.routes.venue_calendar import IST, _is_weekend, _week_start, _ist


class _Res:
    def __init__(self, v): self.v = v
    def scalar_one_or_none(self): return self.v
    def all(self): return self.v


class _Db:
    def __init__(self, entity, rows): self.q = [entity, rows]
    async def execute(self, *_a, **_k): return _Res(self.q.pop(0))


def _run(rows):
    ent = SimpleNamespace(name="Act")
    return asyncio.run(forecast_demand(str(uuid.uuid4()), city=None, months=2, db=_Db(ent, rows), user=None))


def test_forecast_insufficient_history_is_explicit():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = _run([(t0 + timedelta(days=i), 50.0) for i in range(3)])
    assert out["status"] == "insufficient_history" and out["forecast"] is None


def test_forecast_ok_bounds_and_direction():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [(t0 + timedelta(days=2 * i), 20.0 + 2.5 * i) for i in range(16)]  # steadily rising
    out = _run(rows)
    assert out["status"] == "ok"
    for p in out["forecast"]:
        assert 0 <= p["lower_bound"] <= p["predicted_trend_score"] + 1e-6 <= p["upper_bound"] + 1e-3
    assert out["trend_direction"] == "rising"
    assert out["forecast"][0]["date"] > out["history"][-1]["date"]


def test_week_bucketing_is_ist_not_utc():
    # Sunday 19:30 UTC == Monday 01:00 IST -> next week, not weekend
    d = datetime(2026, 11, 8, 19, 30, tzinfo=timezone.utc)   # Sunday UTC
    assert _ist(d).weekday() == 0 and not _is_weekend(_ist(d))
    # Friday 19:30 UTC == Saturday 01:00 IST -> weekend
    f = datetime(2026, 11, 6, 19, 30, tzinfo=timezone.utc)
    assert _is_weekend(_ist(f))
    ws = _week_start(d)
    assert ws.tzinfo is not None and ws.weekday() == 0 and ws.hour == 0
    assert ws.utcoffset() == timedelta(hours=5, minutes=30)

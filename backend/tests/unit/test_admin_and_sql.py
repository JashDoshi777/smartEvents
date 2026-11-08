"""Admin cache-clear route (executive happy path), latest_metric SQL, portfolio helpers."""
import uuid

import pytest
from sqlalchemy.dialects import postgresql

from app.api.routes.admin import clear_cache
from app.core import response_cache
from app.models.user import User, UserRole
from app.services.latest_metric import latest_metric, trend_direction
from app.services.market_scope import market_clause
from app.services.portfolio import GOOD_MIN, STRONG_MIN, health_label, stats_dict


async def test_clear_cache_empties_and_reports():
    response_cache._CACHE["k"] = object()  # type: ignore[assignment]
    u = User(id=uuid.uuid4(), email="e@x.dev", role=UserRole.EXECUTIVE.value)
    out = await clear_cache(u)
    assert out["status"] == "ok" and out["cleared_entries"] >= 1 and out["cache"]["entries"] == 0


def test_clear_cache_route_is_executive_only():
    from main import app
    route = next(r for r in app.routes if getattr(r, "path", "") == "/admin/cache/clear")
    guards = [d.call for d in route.dependant.dependencies]
    assert any(getattr(g, "__name__", "") == "_check" for g in guards)


def test_latest_metric_is_distinct_on_scored_rows_only():
    from sqlalchemy import select
    lm = latest_metric()
    sql = str(select(lm.entity_id).compile(dialect=postgresql.dialect()))
    assert "DISTINCT ON (entity_metrics.entity_id)" in sql
    assert "composite_score IS NOT NULL" in sql
    assert "composite_score IS NOT NULL" not in str(select(latest_metric(scored_only=False).entity_id).compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize("v,exp", [(None, "stable"), (0, "stable"), (2, "stable"), (2.1, "rising"), (-2.1, "falling")])
def test_trend_direction(v, exp):
    assert trend_direction(v) == exp


def test_health_label_bands_and_none():
    assert health_label(None) == "Needs data"
    assert health_label(STRONG_MIN) == "Strong" and health_label(GOOD_MIN) == "Good" and health_label(GOOD_MIN - 0.1) == "Weak"


def test_stats_dict_handles_empty_scope_without_division_by_zero():
    d = stats_dict((0, 0, None, 0, 0))
    assert d["coverage_pct"] == 0.0 and d["avg_score"] is None
    d = stats_dict((10, 5, 41.26, 6, 4))
    assert d == {"total": 10, "scored": 5, "avg_score": 41.3, "domestic": 6, "international": 4, "coverage_pct": 50.0}


def test_market_clauses_compile_and_partition():
    for m in ("india", "global", "all"):
        str(market_clause(m).compile(dialect=postgresql.dialect()))

"""
Cross-page invariants against the live database (skipped when it is unreachable).

Dashboard, Executive and Watchlist must agree: same market split, one row per entity
(newest snapshot), correct ordering, and movers deltas == newest - previous snapshot.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _db_ok() -> bool:
    try:
        from app.core.database import engine
        async with engine.connect() as c:
            await c.execute(text("select 1"))
        return True
    except Exception:
        return False


@pytest.fixture
async def api():
    from app.core.database import engine
    await engine.dispose()  # pooled connections are bound to the previous test's event loop
    if not await _db_ok():
        pytest.skip("database not reachable")
    from main import app
    from app.api.deps import get_current_user
    from app.models.user import User, UserRole
    import uuid
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email="t@t.dev", full_name="T", role=UserRole.ANALYST)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.parametrize("market", ["india", "global", "all"])
async def test_kpis_match_dashboard_summary(api, market):
    k = (await api.get(f"/executive/kpis?market={market}")).json()["entity_portfolio"]
    s = (await api.get(f"/dashboard/summary?market={market}")).json()["hero"]
    assert k["total_tracked"] == s["total_entities"]
    assert k["with_live_metrics"] == s["entities_with_metrics"]
    assert k["avg_composite_score"] == s["avg_composite_score"]


@pytest.mark.parametrize("market", ["india", "global"])
async def test_portfolio_unique_sorted_and_scoped(api, market):
    p = (await api.get(f"/executive/portfolio?market={market}")).json()
    ids = [e["id"] for e in p["portfolio"]]
    assert len(ids) == len(set(ids)), "one row per entity"
    scores = [e["composite_score"] for e in p["portfolio"] if e["composite_score"] is not None]
    assert scores == sorted(scores, reverse=True)
    assert [e["rank"] for e in p["portfolio"]] == list(range(1, len(ids) + 1))
    # None scores sink to the bottom
    flags = [e["composite_score"] is None for e in p["portfolio"]]
    assert flags == sorted(flags)
    total = (await api.get(f"/dashboard/summary?market={market}")).json()["hero"]["total_entities"]
    assert p["total"] == total


async def test_kpis_top_entities_have_no_duplicates(api):
    top = (await api.get("/executive/kpis")).json()["top_entities"]
    names = [t["name"] for t in top]
    assert len(names) == len(set(names))


async def test_alerts_respect_market_scope(api):
    from app.core.database import engine
    async with engine.connect() as c:
        rows = (await c.execute(text("select name from entities where primary_market='India' and coalesce(is_international,false)=false"))).all()
    indian = {r[0] for r in rows}
    alerts = (await api.get("/dashboard/alerts?market=india")).json()["alerts"]
    for a in alerts:
        if a["entity"]:
            assert a["entity"] in indian


async def test_movers_delta_matches_snapshots(api):
    resp = await api.get("/dashboard/movers?market=all&limit=5")
    assert resp.status_code == 200, resp.text[:300]
    m = resp.json()
    assert all(r["delta"] > 0 for r in m["risers"]) and all(r["delta"] < 0 for r in m["fallers"])
    assert [r["delta"] for r in m["risers"]] == sorted((r["delta"] for r in m["risers"]), reverse=True)
    from app.core.database import engine
    for r in (m["risers"] + m["fallers"])[:4]:
        async with engine.connect() as c:
            pts = (await c.execute(text("select composite_score from entity_metrics where entity_id=:i and composite_score is not null order by time desc limit 2"), {"i": r["id"]})).all()
        assert round(pts[0][0], 1) == r["score"] and round(pts[1][0], 1) == r["previous_score"]
        assert abs(round(pts[0][0] - pts[1][0], 1) - r["delta"]) < 0.11

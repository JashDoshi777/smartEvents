"""Live-DB / live-API invariants for entity_attention_weekly and /trends/momentum. Skipped when unreachable."""
import os
import sys
from datetime import date, timedelta

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.environ.get("LIVEIQ_API", "http://localhost:8000")
EMAIL = os.environ.get("LIVEIQ_TEST_EMAIL", "qa@liveiq.dev")
PASSWORD = os.environ.get("LIVEIQ_TEST_PASSWORD", "QaTest#2026")


@pytest.fixture(scope="module")
def conn():
    sa = pytest.importorskip("sqlalchemy")
    try:
        from app.core.config import settings
        c = sa.create_engine(settings.POSTGRES_SYNC_URL, connect_args={"connect_timeout": 10}).connect()
        c.execute(sa.text("select 1 from entity_attention_weekly limit 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database/table unreachable: {exc}")
    yield c
    c.close()


@pytest.fixture(scope="module")
def http():
    try:
        with httpx.Client(base_url=BASE, timeout=90) as c:
            c.get("/health")
            r = c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
            if r.status_code != 200:
                pytest.skip("cannot log in test user")
            c.headers["Authorization"] = f"Bearer {r.json()['tokens']['access_token']}"
            yield c
    except httpx.ConnectError:
        pytest.skip("backend not running")


def test_weekly_table_sane(conn):
    from sqlalchemy import text
    neg = conn.execute(text("select count(*) from entity_attention_weekly where total < 0 or coalesce(wikipedia_views_en,0) < 0 or coalesce(wikipedia_views_hi,0) < 0")).scalar()
    assert neg == 0
    future = conn.execute(text("select max(week_start) from entity_attention_weekly")).scalar()
    assert future is not None
    assert future + timedelta(days=6) < date.today(), "only complete weeks may be stored (no current/future week)"
    bad_monday = conn.execute(text("select count(*) from entity_attention_weekly where extract(isodow from week_start) <> 1")).scalar()
    assert bad_monday == 0
    bad_total = conn.execute(text("select count(*) from entity_attention_weekly where total <> coalesce(wikipedia_views_en,0) + coalesce(wikipedia_views_hi,0)")).scalar()
    assert bad_total == 0


def test_momentum_endpoint_sorted_and_consistent_with_table(http, conn):
    from sqlalchemy import text
    d = http.get("/trends/momentum?market=india&limit=10").json()
    assert d["market"] == "india" and d["entities_with_history"] > 100
    r, f = d["risers"], d["fallers"]
    assert r and f
    assert [x["momentum_pct"] for x in r] == sorted((x["momentum_pct"] for x in r), reverse=True)
    assert [x["momentum_pct"] for x in f] == sorted(x["momentum_pct"] for x in f)
    assert all(x["momentum_pct"] > 0 and x["label"] == "rising" for x in r)
    assert all(x["momentum_pct"] < 0 for x in f)
    assert all(x["views_28d_avg_weekly"] >= d["formula"]["min_baseline_views_per_week"] for x in r + f)
    for x in (r[0], f[0]):
        rows = conn.execute(text("select week_start, total from entity_attention_weekly where entity_id = :e order by week_start desc limit 5"),
                            {"e": x["entity_id"]}).all()
        assert rows[0][1] == x["views_7d"] and rows[0][0].isoformat() == d["as_of_week"]
        base = sum(t for _, t in rows[1:5]) / 4
        assert abs(base - x["views_28d_avg_weekly"]) < 0.2
        assert abs(100 * (x["views_7d"] - base) / base - x["momentum_pct"]) < 0.2


def test_momentum_markets_and_limit(http):
    for m in ("india", "global", "all"):
        r = http.get(f"/trends/momentum?market={m}&limit=3")
        assert r.status_code == 200 and len(r.json()["risers"]) <= 3
    assert http.get("/trends/momentum?market=bogus").status_code == 422

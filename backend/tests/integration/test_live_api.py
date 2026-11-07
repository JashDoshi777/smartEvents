"""
Live API smoke tests — run against a RUNNING backend (default http://localhost:8000).
Skipped automatically if the server is unreachable.

    LIVEIQ_API=http://localhost:8000 pytest tests/integration -q
"""
import os
import time

import httpx
import pytest

BASE = os.environ.get("LIVEIQ_API", "http://localhost:8000")
EMAIL = os.environ.get("LIVEIQ_TEST_EMAIL", "qa@liveiq.dev")
PASSWORD = os.environ.get("LIVEIQ_TEST_PASSWORD", "QaTest#2026")


@pytest.fixture(scope="module")
def http():
    try:
        with httpx.Client(base_url=BASE, timeout=60) as c:
            c.get("/health")
            r = c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
            if r.status_code != 200:
                pytest.skip(f"cannot log in test user ({r.status_code})")
            c.headers["Authorization"] = f"Bearer {r.json()['tokens']['access_token']}"
            yield c
    except httpx.ConnectError:
        pytest.skip("backend not running")


GET_ENDPOINTS = [
    "/dashboard/summary", "/dashboard/summary?market=india", "/dashboard/alerts",
    "/entities/category/artist", "/entities/category/comedian",
    "/trends/breakout", "/trends/breakout?market=india", "/trends/viral", "/trends/regional",
    "/cities/", "/cities/top", "/cities/gaps", "/cities/Mumbai/intelligence",
    "/cities/Mumbai/venues", "/cities/Mumbai/restaurants",
    "/competitors/intelligence", "/competitors/gaps", "/competitors/activity-feed",
    "/social/crisis-alerts", "/pricing/benchmarks",
    "/executive/kpis", "/executive/portfolio", "/recommend/entities",
    "/copilot/models", "/notifications", "/watchlist", "/auth/me",
]


@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_get_endpoint_ok(http, path):
    r = http.get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    assert r.json() is not None


def test_cached_endpoint_is_fast_on_repeat(http):
    http.get("/dashboard/summary")
    t = time.perf_counter()
    r = http.get("/dashboard/summary")
    assert r.headers.get("x-cache") in ("HIT", "STALE")
    assert time.perf_counter() - t < 0.25


def test_dashboard_trending_has_no_duplicate_entities(http):
    ids = [e["id"] for e in http.get("/dashboard/summary").json()["trending_entities"]]
    assert len(ids) == len(set(ids))


def test_india_scope_excludes_international(http):
    d = http.get("/dashboard/summary?market=india").json()
    assert all(not e["is_international"] for e in d["trending_entities"])
    assert d["hero"]["total_entities"] < http.get("/dashboard/summary?market=all").json()["hero"]["total_entities"]


def test_breakout_is_sorted_by_score_and_unique(http):
    preds = http.get("/trends/breakout?limit=20").json()["predictions"]
    scores = [p["composite_score"] for p in preds]
    assert scores == sorted(scores, reverse=True)
    assert len({p["entity_id"] for p in preds}) == len(preds)


def test_all_cities_are_indian(http):
    cities = http.get("/cities/").json()["cities"]
    assert len(cities) >= 12 and all(c.get("country", "India") == "India" for c in cities)


def test_unauthenticated_is_rejected():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        try:
            assert c.get("/dashboard/summary").status_code == 401
        except httpx.ConnectError:
            pytest.skip("backend not running")


def test_login_wrong_password_rejected():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        try:
            assert c.post("/auth/login", json={"email": EMAIL, "password": "nope-nope"}).status_code == 401
        except httpx.ConnectError:
            pytest.skip("backend not running")

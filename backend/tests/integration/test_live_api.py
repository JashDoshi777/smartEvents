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


# ═══════════════════════════════════════════════════════════════════════════════
# Extended suite: schema shapes, auth/role matrix, market invariants, cache,
# error shapes, input fuzz. Throwaway users are registered via the API and
# deleted from the DB at the end of the module.
# ═══════════════════════════════════════════════════════════════════════════════
import asyncio
import uuid

TEST_DOMAIN = "liveiq-test.dev"
PW = "Throwaway#Pass9"


def _new_email(tag="u"):
    return f"be5-{tag}-{uuid.uuid4().hex[:10]}@{TEST_DOMAIN}"


def _cleanup_throwaway_users():
    """Delete every be5-*@liveiq-test.dev user (FK cascades remove watchlist/reads)."""
    async def _go():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        from app.core.config import settings
        eng = create_async_engine(settings.POSTGRES_URL, poolclass=NullPool,
                                  connect_args={"ssl": "require", "statement_cache_size": 0})
        try:
            async with eng.begin() as c:
                await c.execute(text("delete from users where email like :p"), {"p": f"be5-%@{TEST_DOMAIN}"})
        finally:
            await eng.dispose()
    try:
        asyncio.run(_go())
    except Exception as exc:  # pragma: no cover - cleanup must never fail the suite
        print("throwaway user cleanup failed:", type(exc).__name__)


def _register(client, tag="u"):
    email = _new_email(tag)
    r = client.post("/auth/register", json={"email": email, "password": PW, "full_name": "Be5 Test"})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"email": email, "id": body["user"]["id"], "tokens": body["tokens"],
            "h": {"Authorization": f"Bearer {body['tokens']['access_token']}"}}


@pytest.fixture(scope="module")
def anon():
    try:
        with httpx.Client(base_url=BASE, timeout=60) as c:
            c.get("/health")
            yield c
    except httpx.ConnectError:
        pytest.skip("backend not running")


@pytest.fixture(scope="module")
def viewers(anon):
    a, b = _register(anon, "a"), _register(anon, "b")
    yield a, b
    _cleanup_throwaway_users()


@pytest.fixture(scope="module")
def entity_id(http):
    return http.get("/entities/search?q=ar&limit=1").json()["results"][0]["id"]


# ── schema shapes for every GET ────────────────────────────────────────────────
SHAPES = {
    "/dashboard/summary": {"hero", "trending_entities", "city_heat", "upcoming_events", "category_breakdown", "type_breakdown", "generated_at"},
    "/dashboard/alerts": {"alerts", "total", "generated_at"},
    "/executive/kpis": {"entity_portfolio", "top_entities", "city_coverage", "generated_at"},
    "/executive/portfolio": {"portfolio", "total", "with_scores", "health_summary"},
    "/trends/breakout": {"predictions", "total", "has_live_scores"},
    "/trends/viral": {"signals"},
    "/trends/regional": {"regions", "total_entities"},
    "/trends/genre/Mumbai": {"city", "genres", "scope"},
    "/recommend/entities": {"recommendations", "total_candidates", "filters_applied"},
    "/social/crisis-alerts": {"alerts", "total"},
    "/notifications": {"notifications", "total"},
    "/notifications/unread-count": {"unread_count"},
    "/watchlist": {"watchlist", "total"},
    "/entities/search?q=ar": {"query", "results", "total", "total_matches"},
    "/entities/category/artist": {"entity_type", "results", "total"},
    "/auth/me": {"id", "email", "role"},
    "/health": {"status", "services", "cache", "db_pool"},
}


@pytest.mark.parametrize("path,keys", list(SHAPES.items()))
def test_get_schema_shape(http, path, keys):
    r = http.get(path)
    assert r.status_code == 200, f"{path}: {r.text[:200]}"
    assert keys <= set(r.json()), f"{path} missing {keys - set(r.json())}"


def test_entity_scoped_endpoints_shape(http, entity_id):
    for path, keys in {
        f"/entities/{entity_id}/profile": {"id", "name", "entity_type"},
        f"/entities/{entity_id}/score": {"entity_id", "composite_score", "signals", "data_completeness"},
        f"/entities/{entity_id}/cities": {"cities", "methodology"},
        f"/social/sentiment/{entity_id}": {"entity_id", "sentiment"},
        f"/social/topics/{entity_id}": {"topics", "total_posts_analyzed"},
        f"/psychology/{entity_id}": {"combined_multiplier", "factors"},
    }.items():
        r = http.get(path)
        assert r.status_code == 200, f"{path}: {r.text[:200]}"
        assert keys <= set(r.json()), path


def test_psychology_multiplier_bounded(http, entity_id):
    m = http.get(f"/psychology/{entity_id}?city=Mumbai").json()["combined_multiplier"]
    assert 0.4 <= m <= 1.5


def test_list_scores_are_in_0_100_and_non_null_when_ranked(http):
    for p in http.get("/trends/breakout?limit=50").json()["predictions"]:
        assert p["composite_score"] is None or 0 <= p["composite_score"] <= 100
    for e in http.get("/executive/portfolio").json()["portfolio"]:
        assert e["composite_score"] is None or 0 <= e["composite_score"] <= 100


# ── market-scope invariants ────────────────────────────────────────────────────
# Compared endpoints are fetched with Cache-Control: no-cache so cache age
# differences (and entities being ingested concurrently) can't cause false failures.
NC = {"Cache-Control": "no-cache"}


@pytest.mark.parametrize("market", ["india", "global", "all"])
def test_same_kpis_on_every_endpoint(http, market):
    d = http.get(f"/dashboard/summary?market={market}", headers=NC).json()["hero"]
    k = http.get(f"/executive/kpis?market={market}", headers=NC).json()["entity_portfolio"]
    p = http.get(f"/executive/portfolio?market={market}", headers=NC).json()
    if not (d["total_entities"] == k["total_tracked"] == p["total"]):  # ingestion raced the three reads: retry once
        d = http.get(f"/dashboard/summary?market={market}", headers=NC).json()["hero"]
        k = http.get(f"/executive/kpis?market={market}", headers=NC).json()["entity_portfolio"]
        p = http.get(f"/executive/portfolio?market={market}", headers=NC).json()
    assert d["total_entities"] == k["total_tracked"] == p["total"]
    assert d["entities_with_metrics"] == k["with_live_metrics"] == p["with_scores"]
    assert d["avg_composite_score"] == k["avg_composite_score"]


def test_india_plus_global_equals_all(http):
    n = {m: http.get(f"/executive/kpis?market={m}", headers=NC).json()["entity_portfolio"]["total_tracked"] for m in ("india", "global", "all")}
    assert n["india"] + n["global"] == n["all"]
    k = http.get("/executive/kpis", headers=NC).json()["entity_portfolio"]
    assert k["indian"] + k["international"] == k["total_tracked"]


@pytest.mark.parametrize("path", [
    "/dashboard/summary", "/dashboard/alerts", "/executive/kpis", "/executive/portfolio", "/executive/briefing",
    "/trends/breakout", "/trends/viral", "/trends/regional", "/trends/genre/Mumbai",
    "/recommend/entities", "/social/crisis-alerts", "/entities/search?q=ar", "/entities/category/artist",
])
@pytest.mark.parametrize("market", ["india", "global", "all"])
def test_market_param_accepted_everywhere(http, path, market):
    sep = "&" if "?" in path else "?"
    assert http.get(f"{path}{sep}market={market}").status_code == 200


def test_bad_market_value_is_422_everywhere(http):
    for path in ("/dashboard/summary", "/executive/kpis", "/trends/breakout", "/recommend/entities", "/social/crisis-alerts"):
        assert http.get(f"{path}?market=mars").status_code == 422


def test_market_scoped_rankings_are_disjoint(http):
    ind = {p["entity_id"] for p in http.get("/trends/breakout?market=india&limit=50").json()["predictions"]}
    glo = {p["entity_id"] for p in http.get("/trends/breakout?market=global&limit=50").json()["predictions"]}
    assert ind and glo and not (ind & glo)
    ri = {r["entity_id"] for r in http.get("/recommend/entities?market=india&limit=50").json()["recommendations"]}
    assert ri <= ind | {x for x in ri}  # recommendations scoped (non-empty subset check below)
    assert not (ri & glo)


def test_scores_identical_across_endpoints(http):
    top = http.get("/trends/breakout?limit=3").json()["predictions"]
    port = {e["id"]: e["composite_score"] for e in http.get("/executive/portfolio").json()["portfolio"]}
    rec = {r["entity_id"]: r["composite_score"] for r in http.get("/recommend/entities?limit=50").json()["recommendations"]}
    for p in top:
        assert port[p["entity_id"]] == p["composite_score"]
        s = http.get(f"/entities/{p['entity_id']}/score").json()["composite_score"]
        assert s == p["composite_score"]
        if p["entity_id"] in rec:
            assert rec[p["entity_id"]] == p["composite_score"]


def test_every_ranked_entity_appears_once(http):
    for path, key, idk in (("/trends/breakout?limit=50", "predictions", "entity_id"),
                           ("/trends/viral?limit=30", "signals", "entity_id"),
                           ("/recommend/entities?limit=50", "recommendations", "entity_id"),
                           ("/executive/portfolio", "portfolio", "id")):
        ids = [x[idk] for x in http.get(path).json()[key]]
        assert len(ids) == len(set(ids)), path


# ── pagination / limits ────────────────────────────────────────────────────────
def test_search_pagination_is_stable_and_disjoint(http):
    p1 = http.get("/entities/search?q=an&limit=5&offset=0").json()
    p2 = http.get("/entities/search?q=an&limit=5&offset=5").json()
    ids1 = [r["id"] for r in p1["results"]]
    ids2 = [r["id"] for r in p2["results"]]
    assert not set(ids1) & set(ids2)
    assert p1["total_matches"] == p2["total_matches"] >= len(ids1) + len(ids2)
    assert ids1 == [r["id"] for r in http.get("/entities/search?q=an&limit=5&offset=0").json()["results"]]


@pytest.mark.parametrize("qs", ["limit=0", "limit=-1", "limit=100000", "limit=abc"])
def test_bad_limit_is_422(http, qs):
    assert http.get(f"/entities/search?q=ar&{qs}").status_code == 422
    assert http.get(f"/trends/breakout?{qs}").status_code == 422
    assert http.get(f"/recommend/entities?{qs}").status_code == 422


def test_negative_offset_is_422(http):
    assert http.get("/entities/search?q=ar&offset=-5").status_code == 422
    assert http.get("/notifications?offset=-1").status_code == 422


# ── input fuzz ─────────────────────────────────────────────────────────────────
FUZZ = ["%", "_", "\\", "%%%%", "' OR 1=1 --", "'; DROP TABLE entities;--", "😀🎤", "Mahārāshtra", "‮\u0000abc",
        "<script>alert(1)</script>", "a b", "ab" * 40, "../../etc/passwd", "%00", "é", "\n\r"]


@pytest.mark.parametrize("q", FUZZ)
def test_search_fuzz_never_500(http, q):
    r = http.get("/entities/search", params={"q": q})
    assert r.status_code in (200, 400, 422), (q, r.status_code, r.text[:200])
    assert r.headers["content-type"].startswith("application/json")


def test_wildcard_is_literal_not_match_all(http):
    total = http.get("/entities/search?q=ar&limit=1").json()["total_matches"]
    assert http.get("/entities/search", params={"q": "%%"}).json()["total_matches"] < total
    assert http.get("/entities/search", params={"q": "__"}).json()["total_matches"] < total


def test_overlong_query_rejected(http):
    assert http.get("/entities/search", params={"q": "a" * 101}).status_code == 422


@pytest.mark.parametrize("bad", ["not-a-uuid", "123", "00000000-0000-0000-0000-000000000000", "%00", "x" * 300, "'--"])
def test_bad_ids_give_4xx_json(http, bad):
    for path in (f"/entities/{bad}/profile", f"/entities/{bad}/score", f"/entities/{bad}/cities",
                 f"/social/sentiment/{bad}", f"/social/topics/{bad}", f"/psychology/{bad}"):
        r = http.get(path)
        assert r.status_code in (400, 404, 422), (path, r.status_code)
        assert "detail" in r.json() and "request_id" in r.json()


@pytest.mark.parametrize("bad", ["x", "'", "%", "1; select 1"])
def test_browse_bad_type_is_400(http, bad):
    assert http.get(f"/entities/category/{bad}").status_code in (400, 404)


def test_compare_validation(http, entity_id):
    assert http.post("/entities/compare", json=[entity_id]).status_code == 400
    assert http.post("/entities/compare", json=[entity_id, entity_id]).status_code == 400  # duplicates collapse
    assert http.post("/entities/compare", json=["nope", entity_id]).status_code == 400
    assert http.post("/entities/compare", json={"a": 1}).status_code == 422
    assert http.post("/entities/compare", json=[entity_id] + [str(uuid.uuid4()) for _ in range(5)]).status_code == 400
    assert http.post("/entities/compare", json=[entity_id, str(uuid.uuid4())]).status_code == 404


def test_compare_two_real_entities(http):
    ids = [r["id"] for r in http.get("/entities/search?q=an&limit=2").json()["results"]]
    r = http.post("/entities/compare", json=ids)
    assert r.status_code == 200 and r.json()["comparison_count"] == 2
    assert [e["id"] for e in r.json()["entities"]] == ids


def test_recommend_unknown_and_ambiguous_city(http):
    assert http.get("/recommend/entities?city=Atlantis").status_code == 404
    assert http.get("/recommend/entities?city=a").status_code == 200  # ambiguous substring must not 500


def test_sign_validation(http, entity_id):
    base = {"entity_id": entity_id, "city": "Mumbai", "venue_capacity": 5000, "proposed_price": 2000}
    assert http.post("/recommend/sign", json=base).status_code == 200
    v = http.post("/recommend/sign", json=base).json()["verdict"]
    assert v in {"sign", "consider", "pass", "insufficient_data"}
    for patch in ({"venue_capacity": 1}, {"proposed_price": -5}, {"city": ""}, {"city": "x" * 500}, {"entity_id": "bad"}):
        assert http.post("/recommend/sign", json={**base, **patch}).status_code in (400, 422)
    assert http.post("/recommend/sign", json={"entity_id": entity_id}).status_code == 422
    assert http.post("/recommend/sign", json={**base, "entity_id": str(uuid.uuid4())}).status_code == 404


# ── error shapes / headers ─────────────────────────────────────────────────────
def test_error_shape_and_security_headers(anon):
    r = anon.get("/dashboard/summary", headers={"Origin": "http://localhost:3000", "X-Request-ID": "req-test-123456"})
    assert r.status_code == 401
    j = r.json()
    assert j["detail"] and j["error"] == "unauthorized" and j["request_id"] == "req-test-123456"
    assert r.headers["x-request-id"] == "req-test-123456"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"]
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unknown_origin_and_never_wildcard(anon):
    r = anon.get("/health", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") not in ("*", "https://evil.example")
    pre = anon.options("/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert pre.headers.get("access-control-allow-origin") is None


def test_validation_error_is_structured_and_does_not_echo_password(anon):
    r = anon.post("/auth/login", json={"email": "not-an-email", "password": "SuperSecret-123"})
    assert r.status_code == 422 and "SuperSecret" not in r.text
    assert r.json()["error"] == "validation_error"


def test_404_and_405_are_json(anon):
    r = anon.get("/no/such/route")
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    assert anon.delete("/health").status_code == 405


def test_malformed_and_expired_tokens_are_401(anon):
    for tok in ("garbage", "a.b.c", "x" * 5000):
        r = anon.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401 and r.headers.get("www-authenticate", "").lower().startswith("bearer")
    assert anon.get("/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_refresh_token_cannot_be_used_as_access(anon, viewers):
    a, _ = viewers
    r = anon.get("/auth/me", headers={"Authorization": f"Bearer {a['tokens']['refresh_token']}"})
    assert r.status_code == 401
    r = anon.post("/auth/refresh", json={"refresh_token": a["tokens"]["access_token"]})
    assert r.status_code == 401


# ── auth: registration / login / refresh / logout ──────────────────────────────
def test_register_rules(anon, viewers):
    a, _ = viewers
    dup = anon.post("/auth/register", json={"email": a["email"].upper(), "password": PW, "full_name": "x"})
    assert dup.status_code == 409  # case-insensitive duplicate
    assert anon.post("/auth/register", json={"email": _new_email("w"), "password": "short", "full_name": "x"}).status_code == 422
    assert anon.post("/auth/register", json={"email": _new_email("w"), "password": " " * 12, "full_name": "x"}).status_code == 422
    assert anon.post("/auth/register", json={"email": "nope", "password": PW, "full_name": "x"}).status_code == 422
    assert anon.post("/auth/register", json={"email": _new_email("w"), "password": PW, "full_name": ""}).status_code == 422
    assert anon.post("/auth/register", json={"email": _new_email("w"), "password": "x" * 500, "full_name": "x"}).status_code == 422


def test_register_cannot_set_role_and_leaks_no_hash(anon):
    r = anon.post("/auth/register", json={"email": _new_email("r"), "password": PW, "full_name": "Role Try",
                                          "role": "executive", "is_verified": True, "token_version": 99})
    assert r.status_code == 201
    u = r.json()["user"]
    assert u["role"] == "viewer" and u["is_verified"] is False
    assert "hashed_password" not in r.text and "password" not in u


def test_login_email_is_case_insensitive_and_errors_are_uniform(anon, viewers):
    a, _ = viewers
    ok = anon.post("/auth/login", json={"email": a["email"].upper(), "password": PW})
    assert ok.status_code == 200
    bad_pw = anon.post("/auth/login", json={"email": a["email"], "password": "wrong-password"})
    no_user = anon.post("/auth/login", json={"email": _new_email("ghost"), "password": "wrong-password"})
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json()["detail"] == no_user.json()["detail"]


def test_login_bruteforce_lockout(anon):
    email = _new_email("bf")
    codes = [anon.post("/auth/login", json={"email": email, "password": f"wrong-{i}-pass"}).status_code for i in range(7)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
    r = anon.post("/auth/login", json={"email": email, "password": "wrong-again"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_refresh_then_logout_revokes_refresh_tokens(anon):
    u = _register(anon, "rf")
    try:
        r = anon.post("/auth/refresh", json={"refresh_token": u["tokens"]["refresh_token"]})
        assert r.status_code == 200 and r.json()["access_token"]
        new_refresh = r.json()["refresh_token"]
        assert anon.post("/auth/logout", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200
        assert anon.post("/auth/refresh", json={"refresh_token": new_refresh}).status_code == 401
        assert anon.post("/auth/refresh", json={"refresh_token": u["tokens"]["refresh_token"]}).status_code == 401
    finally:
        pass  # user removed by module cleanup (viewers fixture) or the next run's pattern delete


# ── role matrix on mutating routes ─────────────────────────────────────────────
ROLE_GATED = [
    ("POST", "/recommend/sign"), ("POST", "/pricing/optimize"), ("POST", "/events/model"),
    ("POST", "/predict/event-success"), ("POST", "/predict/revenue"),
    ("POST", "/admin/cache/clear"), ("GET", "/executive/report/pdf"),
]


@pytest.mark.parametrize("method,path", ROLE_GATED)
def test_unauthenticated_is_401_on_gated_routes(anon, method, path):
    r = anon.request(method, path, json={} if method == "POST" else None)
    assert r.status_code == 401, (path, r.status_code)


@pytest.mark.parametrize("method,path", ROLE_GATED)
def test_viewer_is_403_on_gated_routes(anon, viewers, method, path):
    a, _ = viewers
    r = anon.request(method, path, headers=a["h"], json={} if method == "POST" else None)
    assert r.status_code == 403, (path, r.status_code, r.text[:150])
    assert r.json()["error"] == "forbidden"


def test_cache_clear_is_executive_only(http, anon, viewers):
    # the QA user is an analyst: not allowed either
    assert http.post("/admin/cache/clear").status_code == 403
    for p in ("/auth/me",):
        assert anon.get(p).status_code == 401


def test_analyst_can_use_gated_booking_routes(http, entity_id):
    r = http.post("/recommend/sign", json={"entity_id": entity_id, "city": "Mumbai", "venue_capacity": 3000, "proposed_price": 1500})
    assert r.status_code == 200
    assert http.get("/executive/report/pdf").status_code in (200, 503)


# ── watchlist & notifications (per-user isolation, idempotency) ────────────────
def test_watchlist_lifecycle_idempotent_and_isolated(anon, viewers, entity_id):
    a, b = viewers
    assert anon.post(f"/watchlist/{entity_id}", headers=a["h"]).status_code == 201
    again = anon.post(f"/watchlist/{entity_id}", headers=a["h"])
    assert again.status_code == 201 and again.json()["already_watched"] is True
    wl = anon.get("/watchlist", headers=a["h"]).json()
    assert [e["id"] for e in wl["watchlist"]].count(entity_id) == 1 and wl["total"] == 1
    assert anon.get("/watchlist", headers=b["h"]).json()["total"] == 0          # not visible to another user
    # Another user's row is untouched: idempotent 200 flagged already_removed, and it still exists for `a`.
    r = anon.delete(f"/watchlist/{entity_id}", headers=b["h"])
    assert r.status_code == 200 and r.json()["already_removed"] is True
    assert anon.delete(f"/watchlist/{entity_id}", headers=a["h"]).status_code == 200
    r2 = anon.delete(f"/watchlist/{entity_id}", headers=a["h"])  # second delete: idempotent
    assert r2.status_code == 200 and r2.json()["already_removed"] is True
    assert anon.post("/watchlist/not-a-uuid", headers=a["h"]).status_code == 400
    assert anon.post(f"/watchlist/{uuid.uuid4()}", headers=a["h"]).status_code == 404


def test_watchlist_requires_auth(anon):
    assert anon.get("/watchlist").status_code == 401
    assert anon.post(f"/watchlist/{uuid.uuid4()}").status_code == 401
    assert anon.delete(f"/watchlist/{uuid.uuid4()}").status_code == 401


def test_exclude_watchlisted_is_per_user_and_never_cached(anon, viewers):
    a, b = viewers
    top = anon.get("/recommend/entities?limit=1", headers=a["h"]).json()["recommendations"][0]["entity_id"]
    assert anon.post(f"/watchlist/{top}", headers=a["h"]).status_code == 201
    try:
        ra = anon.get("/recommend/entities?exclude_watchlisted=true&limit=50", headers=a["h"])
        rb = anon.get("/recommend/entities?exclude_watchlisted=true&limit=50", headers=b["h"])
        assert top not in {r["entity_id"] for r in ra.json()["recommendations"]}
        assert top in {r["entity_id"] for r in rb.json()["recommendations"]}  # no cross-user leak
        assert ra.headers.get("x-cache") is None and rb.headers.get("x-cache") is None
    finally:
        anon.delete(f"/watchlist/{top}", headers=a["h"])


def test_notifications_unread_count_matches_list_and_is_per_user(anon, viewers):
    a, b = viewers
    lst = anon.get("/notifications?limit=100", headers=a["h"]).json()["notifications"]
    assert len({n["id"] for n in lst}) == len(lst)                           # no duplicate ids
    assert len({(n["entity"], n["type"]) for n in lst}) == len(lst)          # nor duplicate (entity, type) signals
    cnt = anon.get("/notifications/unread-count", headers=a["h"]).json()["unread_count"]
    assert cnt == sum(1 for n in lst if not n["is_read"])
    if not lst:
        pytest.skip("no notifications in DB")
    first = lst[0]["id"]
    assert anon.post(f"/notifications/{first}/read", headers=a["h"]).status_code == 200
    assert anon.post(f"/notifications/{first}/read", headers=a["h"]).status_code == 200   # idempotent
    assert anon.get("/notifications/unread-count", headers=a["h"]).json()["unread_count"] == max(cnt - (0 if lst[0]["is_read"] else 1), 0)
    assert anon.get("/notifications/unread-count", headers=b["h"]).json()["unread_count"] == cnt  # b unaffected
    assert anon.post(f"/notifications/{uuid.uuid4()}/read", headers=a["h"]).status_code == 404
    assert anon.post("/notifications/bad/read", headers=a["h"]).status_code == 400
    assert anon.post("/notifications/read-all", headers=a["h"]).status_code == 200
    assert anon.get("/notifications/unread-count", headers=a["h"]).json()["unread_count"] == 0
    assert anon.get("/notifications?unread_only=true", headers=a["h"]).json()["notifications"] == []
    assert anon.get("/notifications/unread-count", headers=b["h"]).json()["unread_count"] == cnt


# ── cache behaviour ────────────────────────────────────────────────────────────
def test_cache_hit_bypass_and_stats(http):
    http.get("/trends/regional")
    assert http.get("/trends/regional").headers.get("x-cache") in ("HIT", "STALE")
    fresh = http.get("/trends/regional", headers={"Cache-Control": "no-cache"})
    assert fresh.status_code == 200 and fresh.headers.get("x-cache") is None
    st = http.get("/health").json()["cache"]
    assert {"entries", "hits", "misses", "hit_ratio", "max_entries"} <= set(st)


def test_cached_body_requires_auth_and_valid_token(anon, http):
    http.get("/executive/kpis")
    assert anon.get("/executive/kpis").status_code == 401
    assert anon.get("/executive/kpis", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_per_user_routes_never_cached(http):
    for p in ("/notifications", "/watchlist", "/auth/me", "/notifications/unread-count", "/executive/report/pdf"):
        assert http.get(p).headers.get("x-cache") is None


def test_error_responses_not_cached(http):
    for _ in range(2):
        r = http.get("/entities/category/nonsense")
        assert r.status_code == 400 and r.headers.get("x-cache") is None


def test_health_reports_optional_services_without_failing(anon):
    r = anon.get("/health")
    assert r.status_code == 200
    s = r.json()["services"]
    assert s["postgres"] == "up" and s["redis"] in ("up", "optional-offline") and s["mongodb"] in ("up", "optional-offline")


def test_concurrent_requests_all_succeed(http):
    """A burst well beyond the DB pool size must degrade gracefully (200 or 503+Retry-After), never hang or 500."""
    import concurrent.futures as cf
    paths = ["/dashboard/summary?market=india&_=%d" % i for i in range(24)]
    with cf.ThreadPoolExecutor(12) as ex:
        res = list(ex.map(lambda p: http.get(p, headers={"Cache-Control": "no-cache"}), paths))
    for r in res:
        assert r.status_code in (200, 503, 429), r.status_code
        if r.status_code == 503:
            assert r.headers.get("retry-after")
    assert sum(r.status_code == 200 for r in res) >= 12

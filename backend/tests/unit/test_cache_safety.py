"""Response cache safety: never cache errors/degraded/per-user variants/role-gated routes."""
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Response
from fastapi.routing import APIRoute

from app.core import response_cache
from app.core.response_cache import ResponseCacheMiddleware, _rule_for
from app.services.auth_service import create_access_token


def _app():
    app = FastAPI()
    app.state.calls = 0
    app.state.fail = False

    @app.get("/dashboard/summary")
    async def summary():
        app.state.calls += 1
        if app.state.fail:
            return Response('{"error":"x"}', status_code=500, media_type="application/json")
        return {"n": app.state.calls}

    @app.get("/executive/briefing")
    async def briefing():
        app.state.calls += 1
        return {"briefing": "AI briefing temporarily unavailable.", "n": app.state.calls}

    @app.get("/recommend/entities")
    async def rec():
        app.state.calls += 1
        return {"n": app.state.calls}

    @app.get("/executive/report/pdf")
    async def pdf():
        app.state.calls += 1
        return {"n": app.state.calls}

    @app.get("/trends/viral")
    async def private():
        app.state.calls += 1
        return Response('{"n":%d}' % app.state.calls, media_type="application/json", headers={"Cache-Control": "private"})

    app.add_middleware(ResponseCacheMiddleware)
    return app


@pytest.fixture(autouse=True)
def _clear():
    response_cache.invalidate_all()
    yield
    response_cache.invalidate_all()


def _c(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _auth():
    return {"Authorization": f"Bearer {create_access_token(uuid4(), 'viewer')}"}


async def _twice(app, path, headers=None):
    async with _c(app) as c:
        h = {**_auth(), **(headers or {})}
        a = await c.get(path, headers=h)
        b = await c.get(path, headers=h)
    return a, b


async def test_error_responses_are_not_cached():
    app = _app()
    app.state.fail = True
    a, b = await _twice(app, "/dashboard/summary")
    assert a.status_code == b.status_code == 500 and app.state.calls == 2
    app.state.fail = False
    c_ = await _twice(app, "/dashboard/summary")
    assert c_[1].headers["x-cache"] == "HIT"


async def test_degraded_body_is_not_cached():
    app = _app()
    await _twice(app, "/executive/briefing")
    assert app.state.calls == 2


async def test_private_cache_control_is_not_cached():
    app = _app()
    await _twice(app, "/trends/viral")
    assert app.state.calls == 2


async def test_per_user_query_variant_bypasses_cache():
    app = _app()
    await _twice(app, "/recommend/entities?exclude_watchlisted=true")
    assert app.state.calls == 2
    app2 = _app()
    a, b = await _twice(app2, "/recommend/entities?exclude_watchlisted=false")
    assert b.headers["x-cache"] == "HIT"


async def test_no_cache_request_header_bypasses_and_does_not_store():
    app = _app()
    await _twice(app, "/dashboard/summary", {"Cache-Control": "no-cache"})
    assert app.state.calls == 2
    assert response_cache.cache_stats()["entries"] == 0


async def test_pdf_and_unauthenticated_never_cached():
    app = _app()
    await _twice(app, "/executive/report/pdf")
    assert app.state.calls == 2
    app2 = _app()
    async with _c(app2) as c:
        await c.get("/dashboard/summary")
        await c.get("/dashboard/summary")
    assert app2.state.calls == 2 and response_cache.cache_stats()["entries"] == 0


async def test_huge_query_strings_are_not_cached():
    app = _app()
    await _twice(app, "/dashboard/summary?x=" + "a" * 600)
    assert app.state.calls == 2


async def test_stats_and_clear():
    app = _app()
    await _twice(app, "/dashboard/summary")
    st = response_cache.cache_stats()
    assert st["entries"] == 1 and st["hits"] >= 1 and st["misses"] >= 1 and st["hit_ratio"] is not None
    assert response_cache.invalidate_all() == 1


def test_no_role_gated_get_route_is_cached():
    """Cache key is path+query only, so any GET covered by a cache rule must not
    depend on the caller's role (require_roles) - otherwise a low-privilege user
    could be served a body computed for a privileged one."""
    from main import app

    def deps(dep):
        yield dep
        for d in dep.dependencies:
            yield from deps(d)

    offenders = []
    for r in app.routes:
        if not isinstance(r, APIRoute) or "GET" not in r.methods:
            continue
        if _rule_for(r.path.replace("{", "x").replace("}", "")) is None and _rule_for(r.path) is None:
            continue
        for d in deps(r.dependant):
            if getattr(d.call, "__name__", "") == "_check":  # require_roles' inner guard
                offenders.append(r.path)
    assert offenders == []

"""Unit tests for the stale-while-revalidate response cache middleware."""
import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.core import response_cache
from app.core.response_cache import ResponseCacheMiddleware
from app.services.auth_service import create_access_token


def _app():
    app = FastAPI()
    app.state.calls = 0

    @app.get("/dashboard/summary")
    async def summary():
        app.state.calls += 1
        return {"n": app.state.calls}

    @app.get("/watchlist")
    async def watchlist():  # per-user route: must never be cached
        app.state.calls += 1
        return {"n": app.state.calls}

    app.add_middleware(ResponseCacheMiddleware)
    return app


@pytest.fixture(autouse=True)
def _clear():
    response_cache.invalidate_all()
    yield
    response_cache.invalidate_all()


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _auth():
    return {"Authorization": f"Bearer {create_access_token(uuid4(), 'viewer')}"}


async def test_second_call_is_served_from_cache():
    app = _app()
    async with _client(app) as c:
        r1 = await c.get("/dashboard/summary", headers=_auth())
        r2 = await c.get("/dashboard/summary", headers=_auth())
    assert r1.headers["x-cache"] == "MISS" and r2.headers["x-cache"] == "HIT"
    assert r1.json() == r2.json() and app.state.calls == 1


async def test_cache_never_serves_without_valid_token():
    app = _app()
    async with _client(app) as c:
        await c.get("/dashboard/summary", headers=_auth())  # prime
        anon = await c.get("/dashboard/summary")
        bad = await c.get("/dashboard/summary", headers={"Authorization": "Bearer garbage"})
    # Falls through to the app (which in this stub app has no auth) but is NOT a cache hit.
    assert "x-cache" not in anon.headers and "x-cache" not in bad.headers


async def test_user_specific_routes_are_not_cached():
    app = _app()
    async with _client(app) as c:
        a = await c.get("/watchlist", headers=_auth())
        b = await c.get("/watchlist", headers=_auth())
    assert "x-cache" not in a.headers and a.json() != b.json()


async def test_concurrent_misses_compute_once():
    app = _app()
    async with _client(app) as c:
        rs = await asyncio.gather(*[c.get("/dashboard/summary", headers=_auth()) for _ in range(8)])
    assert app.state.calls == 1
    assert {r.json()["n"] for r in rs} == {1}


async def test_stale_entry_served_instantly_then_refreshed(monkeypatch):
    app = _app()
    async with _client(app) as c:
        await c.get("/dashboard/summary", headers=_auth())
        for e in response_cache._CACHE.values():  # force fresh window to expire
            e.fresh_until = 0
        stale = await c.get("/dashboard/summary", headers=_auth())
        assert stale.headers["x-cache"] == "STALE" and stale.json()["n"] == 1
        await asyncio.sleep(0.1)  # background refresh
        fresh = await c.get("/dashboard/summary", headers=_auth())
    assert fresh.json()["n"] == 2

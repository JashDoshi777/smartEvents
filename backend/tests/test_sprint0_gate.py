"""
Sprint 0 Gate Tests — All must pass before Sprint 1 begins.
Verifies the app boots, all route stubs are reachable, health check works.
No Docker required — DB/Redis/Mongo connections are mocked in conftest.py.
"""
import pytest


async def test_health_endpoint(client):
    """GATE: /health returns 200 with correct structure."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "services" in data
    assert "postgres" in data["services"]
    assert "redis" in data["services"]
    assert "mongodb" in data["services"]
    # Mocked — all should report 'up'
    assert data["services"]["postgres"] == "up"
    assert data["services"]["redis"] == "up"
    assert data["services"]["mongodb"] == "up"


async def test_root_endpoint(client):
    """Root / returns app metadata."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


PROTECTED_GETS = [
    "/entities/search?q=AP+Dhillon", "/trends/breakout", "/trends/viral", "/cities/", "/cities/gaps",
    "/competitors/intelligence", "/executive/kpis", "/dashboard/summary", "/dashboard/alerts",
    "/recommend/entities", "/notifications", "/watchlist",
]


@pytest.mark.parametrize("path", PROTECTED_GETS)
async def test_protected_routes_require_auth(client, path):
    """Every data route must reject anonymous callers with 401 (never 200/500)."""
    response = await client.get(path)
    assert response.status_code == 401


async def test_entities_search_requires_min_length_when_authed_validation_precedes_auth(client):
    """Validation errors must not leak data to anonymous callers."""
    response = await client.get("/entities/search?q=A")
    assert response.status_code in (401, 422)


async def test_copilot_requires_auth(client):
    response = await client.post("/copilot/chat", json={"message": "hi"})
    assert response.status_code in (401, 422)

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


async def test_entities_search_stub(client):
    """Entity search stub is reachable and returns results key."""
    response = await client.get("/entities/search?q=AP+Dhillon")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


async def test_entities_search_requires_min_length(client):
    """Entity search should reject queries shorter than 2 chars."""
    response = await client.get("/entities/search?q=A")
    assert response.status_code == 422  # FastAPI validation error


async def test_trends_breakout_stub(client):
    """Trends breakout endpoint is reachable."""
    response = await client.get("/trends/breakout")
    assert response.status_code == 200
    assert "predictions" in response.json()


async def test_trends_viral_stub(client):
    """Trends viral signals endpoint is reachable."""
    response = await client.get("/trends/viral")
    assert response.status_code == 200


async def test_cities_list_stub(client):
    """Cities list endpoint is reachable."""
    response = await client.get("/cities/")
    assert response.status_code == 200
    assert "cities" in response.json()


async def test_cities_gaps_before_dynamic_param(client):
    """IMPORTANT: /cities/gaps must NOT be matched as /{city_name} param."""
    response = await client.get("/cities/gaps")
    assert response.status_code == 200
    data = response.json()
    # If this returns {"city": "gaps", ...} then the path conflict bug is present
    assert "city" not in data
    assert "gaps" in data


async def test_competitors_stub(client):
    """Competitor intel endpoint is reachable."""
    response = await client.get("/competitors/intelligence")
    assert response.status_code == 200


async def test_copilot_chat_stub(client):
    """Copilot chat POST endpoint is reachable."""
    response = await client.post("/copilot/chat", json={"question": "test"})
    assert response.status_code == 200


async def test_executive_kpis_stub(client):
    """Executive KPIs endpoint is reachable."""
    response = await client.get("/executive/kpis")
    assert response.status_code == 200


async def test_pricing_optimize_stub(client):
    """Pricing optimizer POST endpoint is reachable with valid body."""
    response = await client.post(
        "/pricing/optimize",
        json={
            "entity_id": "00000000-0000-0000-0000-000000000001",
            "city": "Mumbai",
            "venue_capacity": 5000,
            "proposed_price": 2000.0,
        },
    )
    # 404 = entity not found in mock DB (expected) — endpoint itself is reachable
    # 200 = would mean entity was found (integration test scenario)
    assert response.status_code in (200, 404), f"Unexpected status: {response.status_code}"

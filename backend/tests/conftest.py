"""
LiveIQ — pytest configuration.
Unit tests use SQLite in-memory where possible.
Integration tests (in tests/integration/) require Docker services running.
"""
import pytest
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch


# ─── pytest-asyncio mode (required for 0.23+) ─────────────────────────────
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    return asyncio.DefaultEventLoopPolicy()


def _make_mock_db():
    """
    Create a mock async DB session that satisfies get_db dependency.
    Returns empty/zero results for all execute()/scalar() calls.
    """
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    # scalar() is called with `await db.scalar(...)` — must return a plain int
    mock_session.scalar = AsyncMock(return_value=0)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


async def _mock_get_db():
    """Async generator mock for the get_db FastAPI dependency."""
    yield _make_mock_db()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client for testing API endpoints.
    DB/Redis/Mongo connections are mocked — no Docker needed for unit tests.
    """
    # Mock all external connections so tests run without real infra
    with patch("app.core.database.check_db_connection", new_callable=AsyncMock, return_value=True), \
         patch("app.core.mongodb.check_mongo_connection", new_callable=AsyncMock, return_value=True), \
         patch("app.core.redis_client.check_redis_connection", new_callable=AsyncMock, return_value=True), \
         patch("app.core.mongodb.close_mongo_connection", new_callable=AsyncMock), \
         patch("app.core.redis_client.close_redis_connection", new_callable=AsyncMock):
        from main import app
        from app.core.database import get_db

        # Override get_db with a factory that creates a fresh mock each call
        async def override_get_db():
            yield _make_mock_db()

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
        app.dependency_overrides.clear()

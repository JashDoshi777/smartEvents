"""Keyless news source: query disambiguation, parsers (recorded fixtures), fallback order, cache, worker fallback."""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ingestion import news_free_client as nf

FIX = Path(__file__).resolve().parents[1] / "fixtures"
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(nf, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(nf, "_gdelt_dead_until", 0.0)


def test_query_disambiguates_homonym_film():
    q = nf.build_query("Jawan", "movie", "Bollywood", False, "gdelt")
    assert q.startswith('"Jawan" (') and "film" in q and "Bollywood" in q and q.endswith("sourcecountry:IN")
    assert "sourcecountry" not in nf.build_query("Jawan", "movie", None, False, "gnews")


def test_query_context_by_type_and_international():
    assert "comedian" in nf.build_query("Zakir Khan", "comedian")
    assert "rapper" in nf.build_query("Badshah", "artist", "Indian Hip-Hop")
    assert "IPL" in nf.build_query("Mumbai Indians", "sports_team", "IPL")
    assert "sourcecountry" not in nf.build_query("Ed Sheeran", "artist", "International Pop", True)
    assert '"' not in nf.build_query('Foo "Bar"', "artist").split("(")[0].replace('"Foo Bar"', "")


def test_parse_google_rss_recorded_fixture():
    xml = (FIX / "google_news_arijit.xml").read_text()
    count, capped, titles = nf.parse_google_rss(xml, 7, NOW)
    assert 5 <= count <= 26 and capped is False and titles
    # a window that excludes everything yields 0, not an error
    assert nf.parse_google_rss(xml, 1, datetime(2026, 12, 30, tzinfo=timezone.utc))[0] == 0
    assert nf.parse_google_rss("not xml", 7) is None


def test_parse_gdelt_dedupes_and_windows():
    payload = json.loads((FIX / "gdelt_artlist_shape.json").read_text())
    count, capped, titles = nf.parse_gdelt(payload, 7, NOW)
    assert count == 2 and capped is False        # dup title merged, 3-weeks-old article dropped
    assert nf.parse_gdelt({}, 7) == (0, False, [])
    assert nf.parse_gdelt("Please limit requests to one every 5 seconds") is None


async def test_gdelt_preferred_then_google_fallback_then_none():
    with patch.object(nf, "_gdelt", AsyncMock(return_value=(12, False, [f"Zakir Khan comedy special {i}" for i in range(12)]))), patch.object(nf, "_gnews", AsyncMock()) as g:
        r = await nf.fetch_news_mentions("Zakir Khan", "comedian")
        assert r.source == "gdelt" and r.count == 12
        g.assert_not_called()
    with patch.object(nf, "_gdelt", AsyncMock(return_value=None)), patch.object(nf, "_gnews", AsyncMock(return_value=(7, False, [f"Other Name comedy show {i}" for i in range(7)]))):
        r = await nf.fetch_news_mentions("Other Name", "comedian")
        assert r.source == "google_news_rss" and r.count == 7
    with patch.object(nf, "_gdelt", AsyncMock(return_value=None)), patch.object(nf, "_gnews", AsyncMock(return_value=None)):
        assert await nf.fetch_news_mentions("Third Name", "comedian") is None   # unsourced stays NULL, never 0


async def test_genuine_zero_and_cache():
    with patch.object(nf, "_gdelt", AsyncMock(return_value=(0, False, []))) as g, patch.object(nf, "_gnews", AsyncMock(return_value=(0, False, []))):
        r = await nf.fetch_news_mentions("Nobody", "artist")
        assert r.count == 0
        await nf.fetch_news_mentions("Nobody", "artist")
        assert g.await_count == 1                # second call served from the 6h cache


async def test_worker_falls_back_when_newsapi_429():
    from app.workers import entity_metrics as em
    import httpx

    class Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def search_entity_news(self, *a, **k):
            raise httpx.HTTPError("429 Too Many Requests")

    res = nf.NewsResult(9, "google_news_rss", "q", False, "2026-11-08")
    with patch.object(em, "NewsAPIClient", Boom), patch.object(em, "_NEWSAPI_COOLDOWN_UNTIL", 0.0), \
            patch("app.services.ingestion.news_free_client.fetch_news_mentions", AsyncMock(return_value=res)):
        out = await em._fetch_news_metrics("Jawan", {"entity_type": "movie", "category": "Bollywood"})
    assert out["news_mentions_7d"] == 9 and out["news_source"]["source"] == "google_news_rss"
    assert "controversy_risk" not in out

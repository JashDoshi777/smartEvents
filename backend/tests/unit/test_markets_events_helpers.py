from datetime import timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes.cities import _tier_labels, _composite
from app.api.routes.events import _ist_day
from app.api.routes.pricing import _city_multiplier, CITY_PRICE_MULTIPLIERS


def test_tier_labels_are_built_from_the_cities_returned():
    cities = [SimpleNamespace(name=f"C{i}", tier=1 if i < 8 else 2) for i in range(10)]
    labels = _tier_labels(cities)
    assert set(labels) == {"1", "2"}
    assert "+2 more" in labels["1"] and "C0" in labels["1"]
    assert _tier_labels([SimpleNamespace(name="X", tier=None)]) == {}


def test_composite_ignores_missing_dimensions_and_handles_all_missing():
    c = SimpleNamespace(nightlife_score=80, sports_affinity_score=None, arts_culture_score=60, comedy_market_size=None, music_market_size=100)
    assert _composite(c) == 80.0
    assert _composite(SimpleNamespace(nightlife_score=None, sports_affinity_score=None, arts_culture_score=None, comedy_market_size=None, music_market_size=None)) is None


def test_ist_day_is_the_india_calendar_day():
    start = _ist_day("2026-11-09")
    assert start.astimezone(timezone.utc).isoformat() == "2026-11-08T18:30:00+00:00"   # Mon 00:00 IST == Sun 18:30 UTC
    assert _ist_day("2026-11-09", end=True) - start == timedelta(days=1)
    with pytest.raises(HTTPException):
        _ist_day("09-11-2026")


def test_city_multiplier_uses_tier_defaults_for_uncurated_cities():
    assert _city_multiplier("mumbai", 1) == CITY_PRICE_MULTIPLIERS["mumbai"]
    assert _city_multiplier("surat", 2) == 0.95
    assert _city_multiplier("somewhere", 3) == 0.82
    assert _city_multiplier("unknown", None) == 0.90

"""Unit tests for composite v3 (pure)."""
import math

import pytest

from app.services.scoring.composite import (V3_WEIGHTS, compute_composite_v3, normalise_v3, valid_signals_v3,
                                            compute_composite)

OK = {"youtube": "verified_wikidata", "lastfm": "verified_mbid"}
M = dict(youtube_subscribers=5_000_000, lastfm_listeners=200_000, wikipedia_views_30d=300_000,
         google_trend_relative=0.5, google_trend_basis="topic", news_mentions_7d=40, news_confidence="strict")


def test_anchors():
    assert normalise_v3("youtube", 10_000) == 0
    assert normalise_v3("youtube", 50_000_000) == 100
    assert normalise_v3("lastfm", 1_000) == 0 and normalise_v3("lastfm", 2_000_000) == 100
    assert normalise_v3("wiki", 500) == 0 and normalise_v3("wiki", 2_000_000) == 100
    assert normalise_v3("trends", 0.01) == pytest.approx(0, abs=1e-9) and normalise_v3("trends", 2.0) == pytest.approx(100)
    assert normalise_v3("news", 0) == 0 and normalise_v3("news", 150) == pytest.approx(100)


@pytest.mark.parametrize("sig", ["youtube", "lastfm", "wiki", "trends", "news"])
def test_bounds_and_extremes(sig):
    for v in (-5, 0, 1e-9, 1, 1e3, 1e12, 1e300):
        assert 0 <= normalise_v3(sig, v) <= 100
    xs = [0, 0.001, 0.5, 3, 900, 12_000, 4e5, 3e7, 9e9]
    ys = [normalise_v3(sig, x) for x in xs]
    assert ys == sorted(ys)


def test_weights_sum_to_one():
    for t, w in V3_WEIGHTS.items():
        assert sum(w.values()) == pytest.approx(1.0), t


def test_full_artist():
    r = compute_composite_v3("artist", M, OK)
    assert r["score"] is not None and 0 <= r["score"] <= 100
    assert set(r["signals_used"]) == {"youtube", "wiki", "lastfm", "trends", "news"}
    assert 0.9 <= r["confidence"] <= 1.0 and r["version"] == "v3"


def test_generic_king_unrated():
    # no verified ids: youtube unresolved, no wiki article, lastfm unverified; trends/news alone are not enough
    m = dict(youtube_subscribers=9_000_000, lastfm_listeners=500_000, google_trend_relative=1.5, google_trend_basis="term",
             news_mentions_7d=120, news_confidence="generic_filtered")
    r = compute_composite_v3("artist", m, {"youtube": "unresolved", "lastfm": "name_unverified"})
    assert r["score"] is None and r["confidence"] == 0.0


def test_needs_two_signals_and_one_primary():
    only_wiki = compute_composite_v3("artist", dict(wikipedia_views_30d=1e6), OK)
    assert only_wiki["score"] is None
    trends_news = compute_composite_v3("artist", dict(google_trend_relative=1, google_trend_basis="topic",
                                                       news_mentions_7d=50, news_confidence="strict"), {})
    assert trends_news["score"] is None          # neither youtube nor wiki
    ok = compute_composite_v3("movie", dict(wikipedia_views_30d=1e6, news_mentions_7d=50, news_confidence="strict"), {})
    assert ok["score"] is not None and ok["signals_used"] == ["wiki", "news"]


def test_sports_team_ignores_lastfm():
    m = dict(M, lastfm_listeners=2_000_000)
    v = {"youtube": "verified_wikidata", "lastfm": "verified_mbid"}
    r = compute_composite_v3("sports_team", m, v)
    assert "lastfm" not in r["signals_used"]
    r2 = compute_composite_v3("sports_team", dict(m, lastfm_listeners=1), v)
    assert r["score"] == r2["score"]


def test_lastfm_not_applicable_when_unverified_or_split():
    assert "lastfm" not in valid_signals_v3("artist", M, {"youtube": "verified_wikidata", "lastfm": "name_unverified"})
    assert "lastfm" not in valid_signals_v3("artist", M, {"lastfm": "verified_mbid", "lastfm_detail": {"suspect_split_entry": True}})
    assert "lastfm" in valid_signals_v3("artist", M, {"lastfm": "name_verified_tags"})


def test_invalid_youtube_verdicts_dropped():
    for bad in ("unresolved", "title_mismatch", "metric_from_other_channel", "name_match_unverified", None):
        assert "youtube" not in valid_signals_v3("artist", M, {"youtube": bad})
    for good in ("verified_wikidata", "verified_musicbrainz", "verified_wikidata_handle"):
        assert "youtube" in valid_signals_v3("artist", M, {"youtube": good})


def test_trends_news_validity():
    assert "trends" not in valid_signals_v3("artist", dict(M, google_trend_basis="none"), OK)
    assert "trends" not in valid_signals_v3("artist", dict(M, google_trend_relative=None), OK)
    assert "news" not in valid_signals_v3("artist", dict(M, news_confidence=None), OK)
    assert "news" not in valid_signals_v3("artist", dict(M, news_confidence="ambiguous_skipped"), OK)


def test_missing_signal_not_zero():
    """Renormalised over available weight: dropping a signal must not drag the score towards 0."""
    full = compute_composite_v3("artist", M, OK)["score"]
    m2 = {k: v for k, v in M.items() if k != "news_mentions_7d"}
    part = compute_composite_v3("artist", m2, OK)["score"]
    assert abs(full - part) < 15


def test_monotonic_in_each_signal():
    base = compute_composite_v3("artist", M, OK)["score"]
    for col, mult in (("youtube_subscribers", 5), ("wikipedia_views_30d", 5), ("lastfm_listeners", 5), ("news_mentions_7d", 3),
                      ("google_trend_relative", 3)):
        up = compute_composite_v3("artist", dict(M, **{col: M[col] * mult}), OK)["score"]
        assert up >= base, col


def test_confidence_lower_when_less_evidence():
    full = compute_composite_v3("artist", M, OK)["confidence"]
    thin = compute_composite_v3("artist", dict(wikipedia_views_30d=3e5, youtube_subscribers=5e6), {"youtube": "verified_wikidata"})
    assert thin["score"] is not None and thin["confidence"] < full
    tags = compute_composite_v3("artist", M, {"youtube": "verified_wikidata", "lastfm": "name_verified_tags"})["confidence"]
    assert tags <= full


def test_inputs_garbage():
    r = compute_composite_v3("artist", dict(youtube_subscribers=float("nan"), wikipedia_views_30d="x", news_mentions_7d=None), OK)
    assert r["score"] is None
    assert compute_composite_v3(None, {}, None)["score"] is None
    assert compute_composite_v3("weird_type", dict(wikipedia_views_30d=1e5, google_trend_relative=.2, google_trend_basis="topic"), {})["score"] is not None


def test_tiny_and_huge():
    tiny = compute_composite_v3("artist", dict(youtube_subscribers=1, wikipedia_views_30d=0), {"youtube": "verified_wikidata"})
    assert tiny["score"] == 0
    huge = compute_composite_v3("artist", dict(youtube_subscribers=1e12, wikipedia_views_30d=1e12), {"youtube": "verified_wikidata"})
    assert huge["score"] == 100


def test_v2_still_available():
    assert compute_composite({"youtube_subscribers": 1e6})[0] is not None

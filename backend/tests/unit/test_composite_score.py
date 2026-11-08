"""Composite score v2: bounded, monotonic, missing-source safe, fair to mid-tier acts."""
import math

import pytest

from app.services.scoring.composite import compute_composite, compute_composite_score, TOTAL_WEIGHT
from app.workers.entity_metrics import _compute_composite_score

FULL = dict(lastfm_listeners=500_000, youtube_subscribers=2_000_000, google_trend_score=60, news_mentions_7d=40)


def test_none_when_no_signal():
    assert compute_composite({}) == (None, 0.0)
    assert compute_composite_score({"lastfm_listeners": None}) is None


def test_bounded_0_100_even_for_absurd_inputs():
    big = dict(lastfm_listeners=10**12, youtube_subscribers=10**13, google_trend_score=10**6, news_mentions_7d=10**9)
    assert compute_composite_score(big) == 100.0
    neg = dict(lastfm_listeners=-5, youtube_subscribers=-1, google_trend_score=-50, news_mentions_7d=-3)
    assert compute_composite_score(neg) == 0.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "abc", True, None, [1]])
def test_invalid_values_are_treated_as_missing_not_zero(bad):
    base = compute_composite_score({"google_trend_score": 80})
    with_bad = compute_composite_score({"google_trend_score": 80, "lastfm_listeners": bad})
    assert with_bad == base == 80.0


@pytest.mark.parametrize("key", ["lastfm_listeners", "youtube_subscribers", "google_trend_score", "news_mentions_7d"])
def test_monotonic_in_each_signal(key):
    vals = [0, 10, 1_000, 50_000, 1_000_000, 50_000_000] if key != "google_trend_score" else [0, 10, 40, 70, 100]
    scores = [compute_composite_score({**FULL, key: v}) for v in vals]
    assert scores == sorted(scores)
    assert all(0 <= s <= 100 for s in scores)


def test_missing_sources_renormalise_instead_of_dragging_score():
    only_trend = compute_composite_score({"google_trend_score": 70})
    assert only_trend == 70.0  # not 70 * 0.25
    score, completeness = compute_composite(FULL)
    _, part = compute_composite({"google_trend_score": 70})
    assert completeness == 1.0 and part == round(0.25 / TOTAL_WEIGHT, 2)


def test_data_completeness_is_weight_share():
    _, c = compute_composite({"lastfm_listeners": 1000, "news_mentions_7d": 5})
    assert c == 0.5  # 0.30 + 0.20 of total weight 1.0


def test_mid_tier_indian_act_is_not_crushed():
    # AP Dhillon-like: v1 linear formula scored this ~28; log scale puts a real star well above 50
    s = compute_composite_score(dict(lastfm_listeners=135_441, youtube_subscribers=283_000, google_trend_score=88))
    assert s > 55


def test_global_megastar_beats_mid_tier():
    star = compute_composite_score(dict(lastfm_listeners=7_000_000, youtube_subscribers=100_000_000, google_trend_score=90, news_mentions_7d=100))
    mid = compute_composite_score(dict(lastfm_listeners=130_000, youtube_subscribers=280_000, google_trend_score=90, news_mentions_7d=100))
    assert star > mid and star <= 100


def test_worker_delegates_to_pure_function():
    assert _compute_composite_score(FULL) == compute_composite_score(FULL)
    assert not math.isnan(_compute_composite_score(FULL))


# ── supplementary signals (Spotify popularity, Wikipedia pageviews) ──
def test_extras_absent_leave_score_and_completeness_unchanged():
    assert compute_composite(FULL)[1] == 1.0
    assert compute_composite({"lastfm_listeners": 1000, "news_mentions_7d": 5})[1] == 0.5


def test_extras_do_not_inflate_completeness_and_stay_bounded():
    big = {**FULL, "spotify_popularity": 10**6, "wikipedia_views_30d": 10**15}
    s, c = compute_composite(big)
    assert 0 <= s <= 100 and c == 1.0
    assert compute_composite_score({"spotify_popularity": -5, "wikipedia_views_30d": -1}) == 0.0


@pytest.mark.parametrize("key,vals", [("spotify_popularity", [0, 20, 60, 100]), ("wikipedia_views_30d", [0, 100, 10_000, 1_000_000, 10**8])])
def test_extras_monotonic(key, vals):
    scores = [compute_composite_score({**FULL, key: v}) for v in vals]
    assert scores == sorted(scores) and all(0 <= x <= 100 for x in scores)


def test_wikipedia_alone_gives_a_score_but_low_completeness():
    s, c = compute_composite({"wikipedia_views_30d": 50_000})
    assert s is not None and 0 < s < 100 and c == 0.0

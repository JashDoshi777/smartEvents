"""Pageview aggregation / ISO-week bucketing, momentum maths, anchor ratios (no network)."""
from datetime import date, timedelta

from app.services import attention as at
from app.services import google_trends_relative as G
from app.services.momentum import (MIN_BASELINE, compute_momentum, rank_momentum)

TODAY = date(2026, 11, 9)   # a Monday


def test_iso_week_and_last_complete_week():
    assert at.iso_week_start(date(2026, 11, 9)) == date(2026, 11, 9)
    assert at.iso_week_start(date(2026, 11, 8)) == date(2026, 11, 2)   # Sunday belongs to the previous week
    assert at.last_complete_week_start(TODAY) == date(2026, 11, 2)
    assert at.last_complete_week_start(date(2026, 11, 15)) == date(2026, 11, 2)   # Sunday: week not yet complete
    assert at.last_complete_week_start(date(2026, 11, 16)) == date(2026, 11, 9)
    wk = at.week_range(TODAY, 26)
    assert len(wk) == 26 and wk[-1] == date(2026, 11, 2) and all(w.weekday() == 0 for w in wk)


def test_aggregate_weekly_sums_missing_days_as_zero_and_excludes_partial_week():
    daily = {date(2026, 11, 2): 10, date(2026, 11, 4): 5, date(2026, 11, 8): 1,   # last complete week = 16
             date(2026, 11, 9): 999,                                               # current (incomplete) week: ignored
             date(2026, 10, 26): 7}
    w = at.aggregate_weekly(daily, TODAY, 4)
    assert list(w) == [date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26), date(2026, 11, 2)]
    assert w[date(2026, 11, 2)] == 16 and w[date(2026, 10, 26)] == 7 and w[date(2026, 10, 12)] == 0
    assert 999 not in w.values()


def test_daily_from_items_and_trailing_sum():
    items = [{"timestamp": "2026110100", "views": 4}, {"timestamp": "2026110800", "views": 6}, {"timestamp": "bad", "views": None}] [:2]
    d = at.daily_from_items(items)
    assert d == {date(2026, 11, 1): 4, date(2026, 11, 8): 6}
    assert at.trailing_sum(d, TODAY, 7) == 6          # 2 Nov..8 Nov
    assert at.trailing_sum(d, TODAY, 30) == 10


def test_combine_weeks_none_vs_zero():
    r = at.combine_weeks({date(2026, 11, 2): 5}, None)
    assert r == [(date(2026, 11, 2), 5, None, 5)]


def W(vals, last=date(2026, 11, 2)):
    return {last - timedelta(weeks=len(vals) - 1 - i): v for i, v in enumerate(vals)}


def test_momentum_basic_rising_falling_steady():
    base = [1000, 1020, 980, 1010, 990, 1000, 1005, 995]       # stable history -> z is meaningful
    up = compute_momentum(W(base + [1000, 1000, 1000, 1000, 2000]))
    assert up["momentum_pct"] == 100.0 and up["label"] == "rising" and up["views_7d"] == 2000
    assert up["views_28d_avg_weekly"] == 1000.0
    assert compute_momentum(W(base + [1000] * 4 + [500]))["label"] == "falling"
    assert compute_momentum(W(base + [1000] * 4 + [1100]))["label"] == "steady"


def test_label_needs_robust_z_and_floor():
    # +40% but the entity routinely swings that much: not a trend
    noisy = [600, 1500, 800, 1400, 700, 1600, 900, 1300, 1000, 1000, 1000, 1000, 1400]
    m = compute_momentum(W(noisy))
    assert m["momentum_pct"] == 40.0 and m["label"] == "steady" and abs(m["robust_z"]) < 1.5
    # too little history to compute z: never labelled
    assert compute_momentum(W([1000] * 4 + [2000]))["label"] == "steady"
    # baseline under 1,000/week: no percentage at all
    low = compute_momentum(W([900] * 12 + [3000]))
    assert low["momentum_pct"] is None and low["label"] is None
    assert MIN_BASELINE == 1000.0


def test_rank_uses_only_labelled_movers():
    rows = [{"name": "a", "momentum_pct": 90.0, "label": "steady"}, {"name": "b", "momentum_pct": 60.0, "label": "rising"},
            {"name": "c", "momentum_pct": -40.0, "label": "falling"}]
    r = rank_momentum(rows, 5)
    assert [x["name"] for x in r["risers"]] == ["b"] and [x["name"] for x in r["fallers"]] == ["c"]


def test_momentum_tiny_baseline_is_null():
    m = compute_momentum(W([3, 4, 2, 3, 30]))
    assert m["momentum_pct"] is None and m["label"] is None and m["views_7d"] == 30
    assert MIN_BASELINE > 4


def test_momentum_missing_weeks():
    wk = W([1000, 1000, 1000, 1000, 2000])
    del wk[date(2026, 10, 12)]                       # 3 of 4 prior weeks present: still ok
    assert compute_momentum(wk)["momentum_pct"] == 100.0
    del wk[date(2026, 10, 19)]                       # only 2 prior: NULL
    assert compute_momentum(wk)["momentum_pct"] is None
    # latest week absent for this entity: no comparison on stale data
    assert compute_momentum(W([1000] * 5, last=date(2026, 10, 26)), date(2026, 11, 2))["views_7d"] is None
    assert compute_momentum({})["label"] is None


def test_robust_z_needs_history_and_is_outlier_resistant():
    short = compute_momentum(W([1000] * 6))
    assert short["robust_z"] is None
    hist = [1000, 1100, 900, 1000, 1050, 950, 1000, 980, 1020, 5000]   # one old spike must not wreck the scale
    z = compute_momentum(W(hist + [3000]))["robust_z"]
    assert z is not None and z > 5
    assert compute_momentum(W([1000] * 12))["robust_z"] == 0.0     # constant history: no division by zero


def test_rank_momentum_sorted_and_excludes_null():
    rows = [{"name": "a", "momentum_pct": 10.0}, {"name": "b", "momentum_pct": 90.0}, {"name": "c", "momentum_pct": -50.0},
            {"name": "d", "momentum_pct": -10.0}, {"name": "e", "momentum_pct": None}]
    r = rank_momentum(rows, 2)
    assert [x["name"] for x in r["risers"]] == ["b", "a"]
    assert [x["name"] for x in r["fallers"]] == ["c", "d"]


def test_anchor_ratio_and_delta():
    assert G.anchor_ratio([10, 20], [30, 30]) == 0.5
    assert G.anchor_ratio([0, 0], [50, 50]) == 0.0
    assert G.anchor_ratio([1], [0, 0]) is None and G.anchor_ratio([], [1]) is None
    flat = [10.0] * 28
    assert G.recent_delta_pct(flat) == 0.0
    assert G.recent_delta_pct([10.0] * 21 + [20.0] * 7) == 100.0
    assert G.recent_delta_pct([0.0] * 28) is None                 # prior mean below noise floor
    assert G.recent_delta_pct([5.0] * 10) is None                 # too short
    s = G.summarize([5, 5], [50, 50])
    assert s["relative"] == 0.1


def test_term_allowed_rules():
    assert G.term_allowed("Pritam", "artist", None)
    assert not G.term_allowed("King", "artist", None)
    assert not G.term_allowed("Jawan", "movie", "Jawan (film)")
    assert not G.term_allowed("Some Name", "artist", "Some Name (singer)")
    assert not G.term_allowed("Whatever", "artist", None, ["Q4167410"])

"""'Unrated' (NULL composite) handling shared by routes (pure helpers)."""
from app.services.latest_metric import UNRATED_VERDICT, score_fields
from app.services.portfolio import health_label, stats_dict


def test_score_fields_unrated():
    f = score_fields(None, 0.7, ["wiki"])
    assert f["composite_score"] is None and f["unrated"] is True and f["score_verdict"] == UNRATED_VERDICT
    assert f["score_confidence"] is None and f["signals_used"] == []


def test_score_fields_scored():
    f = score_fields(71.234, 0.8123, ["youtube", "wiki"])
    assert f == {"composite_score": 71.2, "unrated": False, "score_confidence": 0.81, "signals_used": ["youtube", "wiki"],
                 "score_verdict": None}


def test_score_fields_legacy_row_without_confidence():
    f = score_fields(55.0)
    assert f["composite_score"] == 55.0 and f["score_confidence"] is None and f["signals_used"] is None


def test_zero_is_a_score_not_unrated():
    assert score_fields(0.0, 0.2, ["wiki", "youtube"])["unrated"] is False


def test_health_and_stats():
    assert health_label(None) == "Needs data" and health_label(0.0) == "Weak" and health_label(80) == "Strong"
    s = stats_dict((10, 6, 42.34, 8, 2))
    assert s["unrated"] == 4 and s["scored"] == 6 and s["avg_score"] == 42.3
    assert stats_dict((0, 0, None, 0, 0))["unrated"] == 0

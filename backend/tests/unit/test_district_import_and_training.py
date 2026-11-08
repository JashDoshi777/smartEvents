"""District sales importer validation/matching + trainer refusal logic (synthetic fixtures; no DB)."""
from datetime import date
from pathlib import Path

import pytest

from app.services.ingestion import district_sales_import as imp
from app.services.ml import district_training as dt

CITIES = ["Mumbai", "Pune", "Delhi NCR"]


def row(**kw):
    base = dict(event_title="Artist Live", event_date="2025-03-15", city="mumbai", venue_name="Arena", artist_name="Artist",
                category="music", capacity="5000", tickets_sold="4100", gross_revenue_inr="8200000",
                ticket_price_min="1000", ticket_price_max="3500", source_event_id="D-1")
    base.update(kw)
    return base


def test_valid_row_normalised():
    c, e = imp.validate_row(row(), CITIES, today=date(2026, 1, 1))
    assert e == [] and c["city"] == "Mumbai" and c["fill_rate"] == 0.82 and c["source_event_id"] == "D-1"


@pytest.mark.parametrize("patch,needle", [
    ({"event_title": "EXAMPLE—Delete this row"}, "EXAMPLE"),
    ({"event_date": "15 March"}, "event_date"),
    ({"event_date": "2001-01-01"}, "out of range"),
    ({"city": "Atlantis"}, "not a tracked city"),
    ({"category": "polka"}, "category"),
    ({"capacity": "0"}, "capacity"),
    ({"capacity": "abc"}, "not a number"),
    ({"capacity": "12.5"}, "whole number"),
    ({"tickets_sold": "5300"}, "exceeds"),            # fill 1.06 > 1.05
    ({"tickets_sold": "-1"}, "tickets_sold"),
    ({"gross_revenue_inr": "-5"}, "gross_revenue"),
    ({"ticket_price_min": "4000"}, "ticket_price_min >"),
    ({"gross_revenue_inr": "99999999"}, "inconsistent"),
    ({"tickets_sold": "nan"}, "finite"),
])
def test_invalid_rows_rejected(patch, needle):
    c, e = imp.validate_row(row(**patch), CITIES, today=date(2026, 1, 1))
    assert c is None and any(needle in x for x in e), e


def test_fill_boundary_and_cap():
    c, e = imp.validate_row(row(tickets_sold="5250", gross_revenue_inr="10500000"), CITIES, today=date(2026, 1, 1))
    assert e == [] and c["fill_rate"] == 1.0         # 1.05 accepted, stored capped at 1.0


def test_generated_source_id_is_stable():
    r = row(source_event_id="")
    a, _ = imp.validate_row(r, CITIES, today=date(2026, 1, 1))
    b, _ = imp.validate_row(r, CITIES, today=date(2026, 1, 1))
    assert a["source_event_id"] == b["source_event_id"] and a["source_event_id"].startswith("h:")


def test_template_rows_are_refused():
    import csv
    p = Path(__file__).resolve().parents[2] / "data_templates" / "district_sales_template.csv"
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    assert len(rows) == 2 and all(imp.validate_row(r, CITIES)[0] is None for r in rows)
    assert set(imp.REQUIRED) <= set(rows[0])


CANDS = [("1", ["Arijit Singh"]), ("2", ["Arijit Sen"]), ("3", ["Zakir Khan", "Zakir"]), ("4", ["Ali Zafar"]), ("5", ["Ali"])]


def test_match_exact_links_ambiguous_goes_to_review():
    assert imp.fuzzy_match("arijit singh", CANDS).status == "linked"
    twins = [("a", ["Arijit Singh"]), ("b", ["Arijit Singh"])]
    assert imp.fuzzy_match("Arijit Singh", twins).status == "review"     # two identical candidates -> never auto-linked
    close = [("a", ["Rahul Sharma"]), ("b", ["Rahul Sharman"])]
    assert imp.fuzzy_match("Rahul Sharm", close).status in ("review", "none")
    assert imp.fuzzy_match("Completely Unknown Band", CANDS).status == "none"
    m = imp.fuzzy_match("Zakir Khan", CANDS)
    assert m.status == "linked" and m.id == "3"


def test_match_is_conservative_for_subset_names():
    m = imp.fuzzy_match("Ali Zafar Live", [("4", ["Ali Zafar"])])
    assert m.status != "linked"


# ── trainer ───────────────────────────────────────────────────────────────────
def test_eligibility_excludes_incomplete_and_synthetic():
    assert dt.eligible({"total_capacity": 1000, "tickets_sold": 800, "source": "district_sales"})
    assert not dt.eligible({"total_capacity": 1000, "tickets_sold": None, "source": "district"})
    assert not dt.eligible({"total_capacity": 0, "tickets_sold": 0, "source": "district"})
    assert not dt.eligible({"total_capacity": 1000, "tickets_sold": 1200, "source": "district"})
    assert not dt.eligible({"total_capacity": 1000, "tickets_sold": 500, "source": "synthetic"})


def test_trainer_refuses_below_minimum(tmp_path):
    with pytest.raises(dt.InsufficientData) as e:
        dt.require_enough([1] * 149)
    assert "150" in str(e.value) and "Synthetic" in str(e.value)
    dt.require_enough([1] * 150)
    with pytest.raises(dt.InsufficientData):
        dt.train_and_save([[0.0] * 9] * 10, [0.5] * 10, [None] * 10, tmp_path)
    assert list(tmp_path.iterdir()) == []             # nothing written when refusing


def test_train_save_promote_roundtrip(tmp_path):
    import numpy as np
    rng = np.random.default_rng(0)
    X = [[float(rng.uniform(20, 100)), float(rng.uniform(40, 100)), float(rng.uniform(5, 10)), float(rng.integers(0, 6)), 0.0, 60.0, 30.0, 0.0, 50.0] for _ in range(160)]
    yf = [min(1.0, max(0.05, x[0] / 120 + 0.1)) for x in X]
    yp = [1000 + 20 * x[0] for x in X]
    meta = dt.train_and_save(X, yf, yp, tmp_path / "district")
    assert meta["version"] == "v1" and meta["training_rows"] == 160 and meta["metrics"]["fill_rate"]["r2"] > 0.5
    assert (tmp_path / "district" / "v1" / "metadata.json").exists() and meta["data_hash"]
    assert dt.train_and_save(X, yf, yp, tmp_path / "district")["version"] == "v2"
    dt.promote(tmp_path / "district", "v1", tmp_path)
    assert (tmp_path / "promoted.json").read_text().count("district/v1") == 1


def test_engine_reports_provenance(tmp_path, monkeypatch):
    from app.services.ml import pricing_engine as pe
    monkeypatch.setattr(pe, "PROMOTED_PATH", tmp_path / "none.json")
    eng = pe._PricingMLEngine()
    out = eng.predict(composite_score=60, city_music_score=70, venue_capacity=5000, proposed_price=2000)
    assert out["model_provenance"] in ("synthetic-baseline", "rule-based")

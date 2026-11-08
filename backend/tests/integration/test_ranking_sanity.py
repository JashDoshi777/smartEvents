"""Golden-list regression guard for composite v3 against the LIVE DB (read-only; skipped if unreachable).

After `python scripts/recompute_v3.py --apply`:
  * the top 25 India-scoped scored entities include >= 8 well-known Indian acts,
  * no generic-English-word entity ranks without >= 2 verified signals,
  * invariants: composite in [0,100]; scored rows carry confidence + signals_used; < 2 signals or no youtube/wiki -> NULL.
"""
import re
import unicodedata

import pytest

GOLDEN = ["Arijit Singh", "A. R. Rahman", "Badshah", "Diljit Dosanjh", "Yo Yo Honey Singh", "Shreya Ghoshal", "Sonu Nigam",
          "Neha Kakkar", "Anirudh Ravichander", "Pritam", "Divine", "AP Dhillon", "Jubin Nautiyal", "Guru Randhawa",
          "Armaan Malik", "Sidhu Moose Wala", "Karan Aujla", "Shankar Mahadevan", "Zakir Khan", "Mumbai Indians",
          "Chennai Super Kings"]
GENERIC = ["King", "Fighter", "Jawan", "Animal", "Sultaan", "Pathaan", "Baadshah", "Queen"]


def norm(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", s)


@pytest.fixture(scope="module")
def rows():
    sa = pytest.importorskip("sqlalchemy")
    try:
        from app.core.config import settings
        eng = sa.create_engine(settings.POSTGRES_SYNC_URL, connect_args={"connect_timeout": 10})
        with eng.connect() as c:
            r = c.execute(sa.text("""
              select e.name, e.name_aliases al, e.entity_type, e.primary_market, coalesce(e.is_international,false) intl,
                     m.composite_score, m.score_confidence, m.signals_used, m.score_version
              from entities e join lateral (select * from entity_metrics where entity_id=e.id and (composite_score is not null or score_version is not null)
                    order by time desc limit 1) m on true where e.status='active'""")).mappings().all()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database unreachable: {exc}")
    if not any(x["score_version"] == "v3" for x in r):
        pytest.skip("v3 scores not applied yet (run scripts/recompute_v3.py --apply)")
    return r


def india(rows):
    return [r for r in rows if r["primary_market"] == "India" and not r["intl"]]


def test_golden_acts_in_india_top25(rows):
    top = sorted([r for r in india(rows) if r["composite_score"] is not None], key=lambda r: -r["composite_score"])[:25]
    names = set()
    for r in top:
        names |= {norm(r["name"])} | {norm(a) for a in (r["al"] or [])}
    hits = [g for g in GOLDEN if norm(g) in names]
    assert len(hits) >= 8, f"only {len(hits)} golden acts in top 25: {hits}; top = {[r['name'] for r in top]}"


def test_no_generic_name_without_two_verified_signals(rows):
    bad = [r["name"] for r in rows if r["composite_score"] is not None and r["name"] in GENERIC and len(r["signals_used"] or []) < 2]
    assert not bad, bad
    top = sorted([r for r in india(rows) if r["composite_score"] is not None], key=lambda r: -r["composite_score"])[:25]
    assert not [r["name"] for r in top if r["name"] in GENERIC and len(r["signals_used"] or []) < 2]


def test_invariants(rows):
    for r in rows:
        if r["score_version"] != "v3":
            continue
        used = r["signals_used"] or []
        if r["composite_score"] is None:
            assert not (len(used) >= 2 and {"youtube", "wiki"} & set(used)), r["name"]
        else:
            assert 0 <= r["composite_score"] <= 100, r["name"]
            assert r["score_confidence"] is not None and 0 <= r["score_confidence"] <= 1, r["name"]
            assert len(used) >= 2 and {"youtube", "wiki"} & set(used), r["name"]
            if r["entity_type"] != "artist":
                assert "lastfm" not in used, r["name"]

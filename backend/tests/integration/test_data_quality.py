"""
Data-quality invariants asserted against the LIVE database (read-only).
Skipped if the DB is unreachable. Reuses scripts/data_quality_report.run_checks so the
report and the test suite can never disagree: every CRITICAL check must pass.

    pytest tests/integration/test_data_quality.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="module")
def conn():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    try:
        from app.core.config import settings
        eng = sqlalchemy.create_engine(settings.POSTGRES_SYNC_URL, connect_args={"connect_timeout": 10})
        c = eng.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database unreachable: {exc}")
    yield c
    c.close()


@pytest.fixture(scope="module")
def checks(conn):
    import data_quality_report as dq
    return {k["name"]: k for k in dq.run_checks(conn)}


def test_no_critical_failures(checks):
    failed = [f"{k['name']}: {k['detail']}" for k in checks.values() if k["severity"] == "critical" and not k["ok"]]
    assert not failed, "critical data-quality failures:\n" + "\n".join(failed)


def test_core_tables_populated(conn):
    from sqlalchemy import text
    for t, minimum in (("cities", 12), ("venues", 33), ("entities", 294), ("restaurants", 1000)):
        assert conn.execute(text(f"select count(*) from {t}")).scalar() >= minimum, t


def test_city_coordinates_in_india(conn):
    from sqlalchemy import text
    bad = conn.execute(text("select name from cities where lat is not null and (lat not between 6 and 37.5 or lng not between 68 and 97.5)")).all()
    assert not bad, bad


def test_unique_wikidata_qids(conn):
    from sqlalchemy import text
    d = conn.execute(text("select external_ids->>'wikidata_qid' q, count(*) from entities where external_ids ? 'wikidata_qid' group by 1 having count(*)>1")).all()
    assert not d, d


def test_enriched_rows_have_provenance(conn):
    from sqlalchemy import text
    n = conn.execute(text("select count(*) from entities where external_ids ? 'wikidata_qid' and data_provenance is null")).scalar()
    assert n == 0
    n = conn.execute(text("select count(*) from venues where data_provenance is null and (total_capacity is null)=false and venue_type is null")).scalar()
    assert n == 0
    n = conn.execute(text("select count(*) from cities where data_provenance is null")).scalar()
    assert n == 0, "every city row must carry provenance (source/QID) or an explicit curated note"

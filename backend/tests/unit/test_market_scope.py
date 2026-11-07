from sqlalchemy.dialects import postgresql

from app.services.market_scope import market_clause


def _sql(m):
    return str(market_clause(m).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_india_excludes_international_acts():
    sql = _sql("india")
    assert "primary_market = 'India'" in sql and "is_international IS NULL" in sql


def test_global_is_the_complement():
    sql = _sql("global")
    assert "is_international IS true" in sql.lower() or "is_international IS true" in sql


def test_all_is_unfiltered():
    assert _sql("all").lower() in ("true", "1 = 1")

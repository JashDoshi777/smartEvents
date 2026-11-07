"""Market scoping shared by every route that accepts `market=india|global|all`.

"India" = Indian-market entities that are domestic acts (primary_market is
India AND not flagged international). Foreign acts who merely tour India
(Dua Lipa, BLACKPINK ...) belong to "global" even though their target
market is India.
"""
from sqlalchemy import and_, or_, true

from app.models.entity import Entity


def market_clause(market: str):
    if market == "india":
        return and_(Entity.primary_market == "India", or_(Entity.is_international.is_(None), Entity.is_international.is_(False)))
    if market == "global":
        return or_(Entity.primary_market.is_distinct_from("India"), Entity.is_international.is_(True))
    return true()

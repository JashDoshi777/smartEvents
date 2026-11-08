"""Safe city-name resolution shared by the pricing / modeler / competitor / city routes.

`City.name.ilike('%x%')` + `scalar_one_or_none()` raised MultipleResultsFound (HTTP 500) as soon
as two cities matched a fragment ("ra" -> Chandigarh/Ahmedabad...), and let `%`/`_` act as
wildcards. This resolves deterministically: exact (case-insensitive, hyphen == space) first,
then prefix, then substring; ties break by tier then name.
"""
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.city import City


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def norm_city(name: str) -> str:
    return " ".join(name.replace("-", " ").split()).lower()


async def resolve_city(db: AsyncSession, name: Optional[str]) -> Optional[City]:
    if not name or not name.strip():
        return None
    key = norm_city(name)
    esc = escape_like(key)
    rank = case(
        (func.lower(City.name) == key, 0),
        (func.lower(City.name).like(f"{esc}%", escape="\\"), 1),
        else_=2,
    )
    stmt = (
        select(City)
        .where(func.lower(City.name).like(f"%{esc}%", escape="\\"))
        .order_by(rank, City.tier.asc(), City.name.asc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()

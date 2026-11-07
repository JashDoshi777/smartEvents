"""Helper: the most recent EntityMetric row per entity.

entity_metrics is an append-only time series, so a plain JOIN to it returns
one row per *snapshot* and duplicates entities in any ranking. Use
`latest_metric()` to get an aliased EntityMetric that is already
de-duplicated (Postgres DISTINCT ON), then join to it like a normal table.
"""
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.models.metrics import EntityMetric


def latest_metric():
    sub = (
        select(EntityMetric)
        .distinct(EntityMetric.entity_id)
        .order_by(EntityMetric.entity_id, EntityMetric.time.desc())
        .subquery("latest_metric")
    )
    return aliased(EntityMetric, sub)
